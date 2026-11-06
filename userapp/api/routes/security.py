import uuid
from datetime import datetime, timedelta, timezone
import os
from urllib.parse import urlencode
import ipaddress
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.routing import iter_route_contexts
from fastapi.security import HTTPBearer
import httpx
from pydantic import BaseModel
from starlette.responses import JSONResponse, Response, RedirectResponse
from jose import JWTError, jwt
from sqlalchemy.future import select
from passlib.context import CryptContext
from passlib.exc import UnknownHashError

from userapp.api.util import get_one_endpoint
from userapp.core.models.tables import User as UserTable, Token, Project, GroupEffectiveMember
from userapp.core.services.membership import is_group_administrator
from userapp.core.schemas.note import NoteGet
from userapp.core.schemas.users import MeGet, UserGet
from userapp.core.schemas.general import JoinedProjectView
from userapp.api.load_options import user_load_options
from userapp.db import session_generator

pwd_context = CryptContext(
    schemes=["bcrypt", "sha512_crypt"],
    deprecated="auto",
)

STATE_EXPIRATION_MINUTES = 10


def create_password_hash(plain_password: str) -> str:
    """Create a password hash from a plaintext password.

    Uses bcrypt by default.
    """
    hash = pwd_context.hash(plain_password)

    if not verify_password(plain_password, hash):
        raise ValueError("Failed to verify password hash after creation.")

    return hash


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a stored hash.

    Supports both bcrypt ("$2b$" / "$2y$" / "$2a$") and legacy sha512-crypt ("$6$")
    hashes produced by PHP or system crypt(). Returns False for unknown/invalid
    hash formats instead of raising.
    """
    if not password_hash:
        return False

    try:
        return pwd_context.verify(plain_password, password_hash)
    except (UnknownHashError, ValueError, TypeError):
        # Any parsing/format issues should look like an invalid password
        return False


http_bearer = HTTPBearer(auto_error=False)

class TokenData(BaseModel):
    user_id: int
    is_admin: bool
    # Set while a staff member views the site as user_id: the staff member's own id. Every
    # permission check reads user_id and is_admin, so the request behaves exactly as user_id's.
    impersonator_id: int | None = None
    # Ties the login cookie to the CSRF cookie; reused when the login cookie is reissued
    session_id: str | None = None
    # When the login expires (unix time); a reissued cookie never outlives the original login
    exp: int | None = None


IMPERSONATION_MINUTES = 60


def impersonation_enabled() -> bool:
    """Staff may view the site as another user only when ALLOW_IMPERSONATE=true (not for production)"""

    return os.environ.get("ALLOW_IMPERSONATE", "false").lower() == "true"


async def check_impersonation_enabled() -> None:
    """The /impersonate routes do not exist while the feature is off"""

    if not impersonation_enabled():
        raise HTTPException(status_code=404, detail="Not Found")

class ApiTokenData(BaseModel):
    token_id: int
    is_admin: bool

router = APIRouter(
    tags=["Security"],
    responses={
        404: {
            "description": "Not found"
        }
    }
)


async def get_login_token(request: Request) -> str | None:
    """Get the JWT token from the Authorization header or cookies"""

    # If not found, check the cookies
    token = request.cookies.get("login_token")[7:] if request.cookies.get("login_token") else None
    return token


async def get_user_from_cookie(request: Request, token=Depends(get_login_token)) -> TokenData | None:
    """Get the current user from the JWT token in the cookies"""

    # If there wasn't a token include in the request
    if token is None:
        return None

    # Check that the CSRF token is valid if this is a state changing request
    try:
        await csrf_middleware(request)
    except HTTPException:
        return None

    try:
        payload = jwt.decode(
            token, os.environ["SECRET_KEY"], algorithms=["HS256"]
        )
        user_id: int = payload.get("user_id")
        is_admin: bool = payload.get("is_admin", False)
        token_data = TokenData(
            is_admin=is_admin, user_id=user_id,
            impersonator_id=payload.get("impersonator_id"), session_id=payload.get("session_id"),
            exp=payload.get("exp"),
        )
    except JWTError as e:
        return None

    # A "view as" cookie stops working the moment the feature is switched off
    if token_data.impersonator_id is not None and not impersonation_enabled():
        return None
    return token_data


@lru_cache()
def get_ip_whitelist(whitelist_str: str):
    """Parse a comma-separated whitelist of IPs/CIDRs into a list of ipaddress objects"""

    whitelist = []
    whitelist_entries = [entry.strip() for entry in whitelist_str.split(",")]

    for entry in whitelist_entries:
        try:
            # Only CIDR notation is supported in this function
            if "/" in entry:
                network = ipaddress.ip_network(entry, strict=False)
                whitelist.append(network)
        except ValueError:
            continue  # Only allow CIDR

    return whitelist


def check_ip_in_whitelist(ip_str: str, whitelist_str: str) -> bool:
    """Check if an IP address is in a comma-separated whitelist of IPs/CIDRs"""

    try:
        ip = ipaddress.ip_address(ip_str)
        ip_whitelist = get_ip_whitelist(whitelist_str)
        return any(ip in network for network in ip_whitelist)
    except ValueError:
        return False

async def get_auth_from_api_token(request: Request, session=Depends(session_generator), api_token=Depends(http_bearer)) -> ApiTokenData | None:
    """Get the current user from an API token in the Authorization header"""

    if api_token is None:
        return None

    if "TOKEN_IP_WHITELIST" in os.environ and not check_ip_in_whitelist(request.client.host, os.environ["TOKEN_IP_WHITELIST"]):
        return None

    if "." not in api_token.credentials:
        return None

    token_id_str, token_value = api_token.credentials.split(".", 1)

    try:
        token_id = int(token_id_str)
    except ValueError:
        return None

    result = await session.execute(select(Token).where(Token.id == token_id))
    token = result.unique().scalar_one_or_none()

    if token is None:
        return None

    # Check the token matches
    password_is_valid = verify_password(token_value, token.token)

    if not password_is_valid:
        return None

    if token.expires_at is not None and token.expires_at < datetime.now():
        return None

    # Check the token has access to this route. The matched route's own path leaves out
    # prefixes added by parent routers, so look up its full path in the route tree.
    route = request.scope.get('route')
    route_path = next(
        (rc.path for rc in iter_route_contexts(request.app.routes) if rc.original_route is route),
        route.path,
    )
    if (request.method, route_path) not in set([(p.method.value, p.route) for p in token.permissions]):
        return None
    
    return ApiTokenData(token_id=token.id, is_admin=True)


async def is_admin(user_token=Depends(get_user_from_cookie), api_token=Depends(get_auth_from_api_token)):
    """Dependency to check if the user is an admin"""

    return (user_token and user_token.is_admin) or (api_token is not None) or os.environ.get("ALLOW_ADMIN_ACCESS", "false").lower() == "true"


async def check_is_admin(is_admin=Depends(is_admin)):
    """Raises error if not admin, otherwise does nothing"""

    if not is_admin: raise HTTPException(status_code=403, detail="User is not an admin")


async def is_user(user_id: int, user_token=Depends(get_user_from_cookie)):
    """Dependency to check if the user is the one currently logged in or an admin"""

    if user_token and (user_token.user_id == user_id):
        return True

    return False


async def check_is_user(is_user=Depends(is_user), is_admin=Depends(is_admin)):
    """Raises error if not the user or admin, otherwise does nothing"""

    if not is_user and not is_admin: raise HTTPException(status_code=403, detail="Non-Admin user operating on data that doesn't belong to them.")


async def check_can_administer_group(group_id: int, session=Depends(session_generator), is_admin=Depends(is_admin), user_token=Depends(get_user_from_cookie)) -> None:
    """Staff, or an effective member of the group's owner_group, can edit its membership"""

    if is_admin:
        return
    if user_token and await is_group_administrator(session, user_token.user_id, group_id):
        return
    raise HTTPException(status_code=403, detail="User is not an administrator of this group")


# The design lets exactly the same people view a group as administer it
check_can_view_group = check_can_administer_group


async def _get_project_or_404(session, project_id: int) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def check_can_administer_project_members(project_id: int, session=Depends(session_generator), is_admin=Depends(is_admin), user_token=Depends(get_user_from_cookie)) -> None:
    """Staff, or an administrator of the project's project_group, can edit who is in the project"""

    if is_admin:
        return
    project = await _get_project_or_404(session, project_id)
    if user_token and project.project_group_id is not None \
            and await is_group_administrator(session, user_token.user_id, project.project_group_id):
        return
    raise HTTPException(status_code=403, detail="User is not an administrator of this project")


async def check_can_edit_project(project_id: int, session=Depends(session_generator), is_admin=Depends(is_admin), user_token=Depends(get_user_from_cookie)) -> None:
    """Staff, or an effective member of the project's pi_group, can edit the project's metadata"""

    if is_admin:
        return
    project = await _get_project_or_404(session, project_id)
    if user_token and project.pi_group_id is not None:
        is_pi = await session.scalar(
            select(GroupEffectiveMember.user_id).where(
                GroupEffectiveMember.group_id == project.pi_group_id,
                GroupEffectiveMember.user_id == user_token.user_id,
            ).limit(1)
        )
        if is_pi is not None:
            return
    raise HTTPException(status_code=403, detail="User is not a PI of this project")


async def is_authenticated(user_token=Depends(get_user_from_cookie), api_token=Depends(get_auth_from_api_token)):
    """Dependency to check if the user is authenticated"""

    return user_token or api_token


async def check_is_authenticated(is_authenticated=Depends(is_authenticated)):
    """Raises error if not authenticated, otherwise does nothing"""

    if not is_authenticated: raise HTTPException(status_code=401, detail="User is not authenticated")


def create_login_token(expires_delta: timedelta | None = None, **data):
    """Create a JWT token"""

    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=60 * 8)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, os.environ["SECRET_KEY"], algorithm="HS256"
    )
    return encoded_jwt


def safe_next_path(next_path: str | None) -> str:
    """Return next_path if it is a same-site path, otherwise "/".

    Browsers read "//host" as another site, treat "\\" as "/" and drop tabs and
    newlines, so "//evil.com", "/\\evil.com" and "/\\t/evil.com" all leave the site.
    """

    if (
        not next_path
        or not next_path.startswith("/")
        or next_path.startswith("//")
        or "\\" in next_path
        or any(ord(c) < 0x20 or ord(c) == 0x7f for c in next_path)
    ):
        return "/"
    return next_path


def create_state_token(state: str, next_path: str | None = None) -> str:
    """Create a short-lived, signed/encrypted token for the OIDC state value.

    Optionally embeds the original path the user was on (next_path) so that
    we can redirect back to it after successful login.
    """

    expires_delta = timedelta(minutes=STATE_EXPIRATION_MINUTES)
    to_encode = {"state": state, "type": "oidc_state"}
    if next_path is not None:
        to_encode["next_path"] = next_path

    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, os.environ["SECRET_KEY"], algorithm="HS256")


def decode_state_token(token: str) -> dict | None:
    """Decode a state token and return its payload, or None if invalid."""

    try:
        payload = jwt.decode(token, os.environ["SECRET_KEY"], algorithms=["HS256"])
        if payload.get("type") != "oidc_state":
            return None
        return payload
    except JWTError:
        return None


def verify_state_token(token: str, expected_state: str) -> bool:
    """Verify that the state token is valid and matches the expected raw state."""

    payload = decode_state_token(token)
    if payload is None:
        return False
    return payload.get("state") == expected_state


async def csrf_middleware(request: Request):
    """CSRF protection middleware - Signed Double Submit Cookie Pattern"""

    if request.method in ("POST", "PUT", "DELETE", "PATCH"):

        header_csrf_token = request.headers.get("X-CSRF-Token")
        login_token = request.cookies.get("login_token")[7:] if request.cookies.get("login_token") else None

        if header_csrf_token is None or login_token is None:
            raise HTTPException(status_code=403, detail="Missing CSRF token")

        try:
            header_csrf_payload = jwt.decode(header_csrf_token, os.environ["SECRET_KEY"], algorithms=["HS256"])
            login_token_payload = jwt.decode(login_token, os.environ["SECRET_KEY"], algorithms=["HS256"])
        except JWTError:
            raise HTTPException(status_code=403, detail="Invalid CSRF token, invalid or expired")

        # Verify that the session IDs match
        if header_csrf_payload.get("session_id") != login_token_payload.get("session_id"):
            raise HTTPException(status_code=403, detail="CSRF token mismatch")


async def get_oidc_config() -> dict:
    """Fetch the OIDC provider configuration from the discovery URL"""

    async with httpx.AsyncClient(timeout=10.0) as client:
        oidc_config_resp = await client.get(
            os.environ["OIDC_DISCOVERY_URL"]
        )

    oidc_config_resp.raise_for_status()
    oidc_config = oidc_config_resp.json()

    if "authorization_endpoint" not in oidc_config:
        raise HTTPException(status_code=500, detail="OIDC provider configuration is missing authorization endpoint")

    if "token_endpoint" not in oidc_config:
        raise HTTPException(status_code=500, detail="OIDC provider configuration is missing token endpoint")

    if "jwks_uri" not in oidc_config:
        raise HTTPException(status_code=500, detail="OIDC provider configuration is missing JWKS URI")

    return oidc_config


async def get_oidc_public_keys() -> dict:
    """Fetch the OIDC provider public keys from the JWKS URL"""

    oidc_config = await get_oidc_config()

    async with httpx.AsyncClient(timeout=10.0) as client:
        jwks_resp = await client.get(
            oidc_config["jwks_uri"]
        )

    jwks_resp.raise_for_status()
    jwks = jwks_resp.json()

    if "keys" not in jwks:
        raise HTTPException(status_code=500, detail="OIDC JWKS response is missing keys")

    return jwks


@router.get("/login")
async def login_user(request: Request):
    """Begin Auth Code Flow - redirecting to OIDC provider for login.

    Stores the original path ("next") in the state cookie so that the
    callback can redirect back to it after successful authentication.
    """

    oidc_config = await get_oidc_config()

    # Determine where to return after login. Prefer explicit "next" query
    # parameter, otherwise fall back to the current path.
    next_path = safe_next_path(request.query_params.get("next"))

    # Generate a random state and store an encrypted/signed version in a cookie
    raw_state = str(uuid.uuid4())
    state_token = create_state_token(raw_state, next_path=next_path)

    redirect_uri = f"https://{request.url.hostname}/auth/oidc/callback" if 'PYTHON_ENV' in os.environ and os.environ['PYTHON_ENV'] == "production" else "http://localhost/auth/oidc/callback"

    auth_params = {
        "response_type": "code",
        "client_id": os.environ["OIDC_CLIENT_ID"],
        "redirect_uri": redirect_uri,
        "scope": "openid profile email",
        "state": raw_state,
    }

    auth_url = f"{oidc_config["authorization_endpoint"]}?{urlencode(auth_params)}"

    redirect_response = RedirectResponse(auth_url)

    # Store the encrypted state token in a secure cookie for later verification
    redirect_response.set_cookie(
        key="oidc_state",
        value=state_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=STATE_EXPIRATION_MINUTES * 60,
    )

    return redirect_response


@router.get("/auth/oidc/callback")
async def oidc_callback(request: Request, response: Response, session=Depends(session_generator)):
    """OIDC Callback endpoint to complete login.

    After successful authentication, redirect the user back to the original
    page they came from (if available in the state cookie).
    """

    code = request.query_params.get("code")
    state = request.query_params.get("state")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    # Validate OIDC state against the encrypted cookie
    state_cookie = request.cookies.get("oidc_state")
    state_payload = decode_state_token(state_cookie) if state_cookie else None
    if not state or state_payload is None or state_payload.get("state") != state:
        raise HTTPException(status_code=400, detail="Invalid or missing OIDC state")

    oidc_config = await get_oidc_config()

    redirect_uri = f"https://{request.url.hostname}/auth/oidc/callback" if 'PYTHON_ENV' in os.environ and os.environ['PYTHON_ENV'] == "production" else "http://localhost/auth/oidc/callback"

    # Exchange the authorization code for tokens
    async with httpx.AsyncClient(timeout=10.0) as client:
        token_resp = await client.post(
            oidc_config["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": os.environ["OIDC_CLIENT_ID"],
                "client_secret": os.environ["OIDC_CLIENT_SECRET"],
            },
        )

    token_resp.raise_for_status()
    token_data = token_resp.json()

    id_token = token_data.get("id_token")
    if not id_token:
        raise HTTPException(status_code=500, detail="ID token not provided by OIDC provider")

    # Decode the ID token to get user info
    try:
        oidc_public_keys = await get_oidc_public_keys()
        id_token_payload = jwt.decode(id_token, oidc_public_keys, access_token=token_data['access_token'], audience=os.environ["OIDC_CLIENT_ID"])
        netid = id_token_payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=500, detail="Failed to decode ID token")

    if not netid:
        raise HTTPException(status_code=500, detail="ID token missing required user information")

    # Look up the user in the database
    result = await session.execute(select(UserTable).where(UserTable.netid == netid))
    user = result.scalars().first()

    # If there is no user, create one
    if user is None:
        # Call out to the userinfo endpoint with the access token
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                user_info_resp = await client.get(
                    oidc_config["userinfo_endpoint"],
                    headers={
                        "Authorization": f"Bearer {token_data['access_token']}"
                    },
                )
                user_info_resp.raise_for_status()
                user_info = user_info_resp.json()

                # name is required so fallback to netid if no name is found
                user = UserTable(
                    name=user_info.get("name") or user_info.get("sub"),
                    email1=user_info.get("email", None),
                    netid=user_info.get("sub"),
                    username=user_info.get("sub"),
                    active=False,
                    is_admin=False,
                )
                session.add(user)
                await session.flush()
                await session.refresh(user)
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to fetch user info from OIDC provider")

    # Determine where to send the user after login
    next_path = state_payload.get("next_path") if state_payload else None

    # Checked again here so the redirect stays on this site even if /login changes
    redirect_target = safe_next_path(next_path)

    response = RedirectResponse(url=redirect_target)

    session_id = str(uuid.uuid4())
    response.set_cookie(
        "login_token",
        f"Bearer {create_login_token(user_id=user.id, is_admin=user.is_admin, session_id=session_id)}",
        httponly=True,
        samesite="strict"
    )
    response.set_cookie(
        "csrf_token",
        create_login_token(session_id=session_id, random_value=str(uuid.uuid4())),
        httponly=False,
        samesite="strict"
    )

    return response


@router.post("/logout")
async def logout_user(response: Response):
    response.delete_cookie("login_token")
    return {"message": "Logout successful"}


async def _me(session, user_token: TokenData) -> MeGet:
    """The user the session runs as, with the staff member behind it when it is a "view as" session"""

    user = await get_one_endpoint(session, UserTable, user_token.user_id, load_options=user_load_options)
    me = MeGet.model_validate(user)
    me.can_impersonate = impersonation_enabled() and bool(user.is_admin) and user_token.impersonator_id is None
    if user_token.impersonator_id is not None:
        # None if the staff member was deleted meanwhile; the session then ends with the cookie
        staff = await session.get(UserTable, user_token.impersonator_id)
        me.impersonator = UserGet.model_validate(staff) if staff is not None else None
    return me


def _set_login_cookie(response: Response, user: UserTable, current: TokenData, expires_at: datetime | None = None, **extra) -> None:
    """Reissue the login cookie for *user* with the same cookie attributes as the OIDC callback.

    session_id is kept so the CSRF cookie stays valid, and the new cookie expires when the
    original login would have (or at expires_at if that is sooner): viewing as someone and
    coming back must not stretch a login past what OIDC granted."""

    login_ends = datetime.fromtimestamp(current.exp, timezone.utc) if current.exp else datetime.now(timezone.utc)
    ends = min(login_ends, expires_at) if expires_at else login_ends
    token = create_login_token(
        expires_delta=ends - datetime.now(timezone.utc),
        user_id=user.id, is_admin=user.is_admin, session_id=current.session_id, **extra,
    )
    response.set_cookie("login_token", f"Bearer {token}", httponly=True, samesite="strict")


@router.get("/me")
@router.post("/me", include_in_schema=False) # Added for testing only
async def get_current_user(user_token=Depends(get_user_from_cookie), session=Depends(session_generator)) -> MeGet:
    """Get the current user"""

    if user_token:
        return await _me(session, user_token)
    else:
        raise HTTPException(status_code=401, detail="Not authenticated")


@router.post("/impersonate/stop", tags=["Security"], dependencies=[Depends(check_impersonation_enabled)])
async def stop_impersonating(
    response: Response,
    user_token=Depends(get_user_from_cookie),
    session=Depends(session_generator),
) -> MeGet:
    """End a "view as" session: the login cookie goes back to the staff member, with the is_admin
    they have now (a staff member who lost it meanwhile gets a plain user session)."""

    if user_token is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if user_token.impersonator_id is None:
        raise HTTPException(status_code=400, detail="Not viewing as another user")

    staff = await session.get(UserTable, user_token.impersonator_id)
    if staff is None:
        # Nobody to go back to: log the session out (headers on an HTTPException are dropped)
        gone = JSONResponse(status_code=401, content={"detail": "The logged-in user no longer exists"})
        gone.delete_cookie("login_token")
        return gone

    _set_login_cookie(response, staff, user_token)
    return await _me(session, TokenData(user_id=staff.id, is_admin=bool(staff.is_admin)))


@router.post("/impersonate/{user_id}", tags=["Security"], dependencies=[Depends(check_impersonation_enabled)])
async def impersonate_user(
    user_id: int,
    response: Response,
    user_token=Depends(get_user_from_cookie),
    session=Depends(session_generator),
) -> MeGet:
    """View the site as another user: staff only, and only with ALLOW_IMPERSONATE=true.

    Replaces the login cookie with one for user_id, carrying the target's own is_admin and the
    staff member's id as impersonator_id. From then on every request, read or write, is permitted
    and answered exactly as it would be for that user, and audit rows name that user as the actor.
    Expires after an hour. Calling it while already viewing as someone restarts from the staff
    member, it never chains.
    """

    if user_token is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    staff_id = user_token.impersonator_id or user_token.user_id
    staff = await session.get(UserTable, staff_id)
    if staff is None:
        raise HTTPException(status_code=401, detail="The logged-in user no longer exists")
    # The database, not the cookie, decides: a "view as" cookie carries the target's flag, and a
    # staff member demoted during their login must not keep this (API tokens and
    # ALLOW_ADMIN_ACCESS do not grant it either, there is no real person to come back to)
    if not staff.is_admin:
        raise HTTPException(status_code=403, detail="User is not an admin")
    if user_id == staff_id:
        raise HTTPException(status_code=400, detail="Already logged in as this user; use /impersonate/stop")
    target = await session.get(UserTable, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    _set_login_cookie(
        response, target, user_token,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=IMPERSONATION_MINUTES),
        impersonator_id=staff.id,
    )
    return await _me(session, TokenData(user_id=target.id, is_admin=bool(target.is_admin), impersonator_id=staff.id))
