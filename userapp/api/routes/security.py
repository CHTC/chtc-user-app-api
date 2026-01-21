import uuid
from datetime import datetime, timedelta, timezone
import os
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer
import httpx
from pydantic import BaseModel
from starlette.responses import Response, RedirectResponse
from jose import JWTError, jwt
from sqlalchemy.future import select
from passlib.context import CryptContext
from passlib.exc import UnknownHashError

from userapp.core.schemas.general import Login
from userapp.core.models.tables import User as UserTable, Token
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
    username: str
    user_id: int
    is_admin: bool

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
        username: str = payload.get("username")
        user_id: int = payload.get("user_id")
        is_admin: bool = payload.get("is_admin", False)
        token_data = TokenData(username=username, is_admin=is_admin, user_id=user_id)
    except JWTError as e:
        return None

    return token_data


async def get_auth_from_api_token(request: Request, session=Depends(session_generator), api_token=Depends(http_bearer)) -> ApiTokenData | None:
    """Get the current user from an API token in the Authorization header"""

    if api_token is None:
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
    
    return ApiTokenData(token_id=token.id, is_admin=True)


async def is_admin(user_token=Depends(get_user_from_cookie), api_token=Depends(get_auth_from_api_token)):
    """Dependency to check if the user is an admin"""

    return (user_token and user_token.is_admin) or (api_token is not None)


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
    next_path = request.query_params.get("next") or "/"

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

    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    # Determine where to send the user after login
    next_path = state_payload.get("next_path") if state_payload else None

    # Default to root if we don't have a next_path
    redirect_target = next_path or "/"

    # Ensure redirect_target is a relative path to avoid open redirects
    if not redirect_target.startswith("/"):
        redirect_target = "/" + redirect_target

    response = RedirectResponse(url=redirect_target)

    session_id = str(uuid.uuid4())
    response.set_cookie(
        "login_token",
        f"Bearer {create_login_token(username=user.username, user_id=user.id, is_admin=user.is_admin, session_id=session_id)}",
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


@router.get("/me")
@router.post("/me", include_in_schema=False) # Added for testing only
async def get_current_user(user_token=Depends(get_user_from_cookie), api_token=Depends(get_auth_from_api_token)):
    """Get the current user"""

    if user_token:
        return {"username": user_token.username, "is_admin": user_token.is_admin, "user_id": user_token.user_id}
    elif api_token:
        return {"token_id": api_token.token_id, "is_admin": True}
    else:
        raise HTTPException(status_code=401, detail="Not authenticated")
