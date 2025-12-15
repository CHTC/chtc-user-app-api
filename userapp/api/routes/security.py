import uuid
from datetime import datetime, timedelta, timezone
import os
from typing import Annotated

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from starlette.responses import Response
from jose import JWTError, jwt
from sqlalchemy.future import select
from passlib.context import CryptContext
from passlib.exc import UnknownHashError

from userapp.core.schemas.general import Login
from userapp.core.schemas.users import User as UserSchema
from userapp.core.models.tables import User as UserTable
from userapp.db import session_generator

pwd_context = CryptContext(
    schemes=["bcrypt", "sha512_crypt"],
    deprecated="auto",
)


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
http_basic = HTTPBasic(auto_error=False)

class TokenData(BaseModel):
    username: str
    user_id: int
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
    await csrf_middleware(request)

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


async def get_user_from_basic_auth(credentials: Annotated[HTTPBasicCredentials, Depends(http_basic)], session=Depends(session_generator)) -> UserSchema | None:
    """Get the current user from basic auth header"""

    if credentials is None:
        return None

    result = await session.execute(select(UserTable).where(UserTable.username == credentials.username))
    user = result.unique().scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Check the password matches (supports bcrypt and sha512-crypt "$6$" hashes)
    password_is_valid = verify_password(credentials.password, user.password)

    return user if password_is_valid else None


async def is_admin(user_token=Depends(get_user_from_cookie), basic_user=Depends(get_user_from_basic_auth)):
    """Dependency to check if the user is an admin"""

    if not (user_token and user_token.is_admin) and not (basic_user and basic_user.is_admin):
        raise HTTPException(status_code=403, detail="User is not an admin")

    return True


async def is_user(user_id: int, user_token=Depends(get_user_from_cookie), basic_user=Depends(get_user_from_basic_auth)):
    """Dependency to check if the user is the one currently logged in or an admin"""

    # If admin then allow
    if (user_token and user_token.is_admin) or (basic_user and basic_user.is_admin):
        return True

    # If user is operating on data belonging to themselves then allow
    if user_token (user_token.user_id == user_id):
        return True

    raise HTTPException(status_code=403, detail="Non-Admin user operating on data that doesn't belong to them.")


async def is_authenticated(user_token=Depends(get_user_from_cookie), basic_user=Depends(get_user_from_basic_auth)):
    """Dependency to check if the user is authenticated"""

    if not user_token and not basic_user:
        raise HTTPException(status_code=401, detail="User is not authenticated")

    return True


async def user(user_token=Depends(get_user_from_cookie), basic_user=Depends(get_user_from_basic_auth)):
    """Dependency to get the current user or raise 401"""

    if user_token:
        return user_token
    elif basic_user:
        return basic_user
    else:
        raise HTTPException(status_code=401, detail="User is not authenticated")


def create_token(expires_delta: timedelta | None = None, **data):
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


@router.post("/login")
async def login_user(response: Response, login: Login, session=Depends(session_generator)):

    result = await session.execute(select(UserTable).where(UserTable.username == login.username))
    user = result.scalars().first()

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Check the password matches (supports bcrypt and sha512-crypt "$6$" hashes)
    password_is_valid = verify_password(login.password, user.password)

    if password_is_valid:
        session_id = str(uuid.uuid4())
        response.set_cookie(
            "login_token",
            f"Bearer {create_token(username=user.username, user_id=user.user_id, is_admin=user.is_admin, session_id=session_id)}",
            httponly=True,
            samesite="strict"
        )
        response.set_cookie(
            "csrf_token",
            create_token(session_id=session_id, random_value=str(uuid.uuid4())),
            httponly=False,
            samesite="strict"
        )
        return {"message": "Login successful"}
    else:
        raise HTTPException(status_code=401, detail="Invalid password")


@router.post("/logout")
async def logout_user(response: Response):
    response.delete_cookie("login_token")
    return {"message": "Logout successful"}


@router.get("/me")
@router.post("/me") # Added for testing only
async def get_current_user(user_token=Depends(get_user_from_cookie), basic_user=Depends(get_user_from_basic_auth)):
    """Get the current user"""

    if user_token:
        return {"username": user_token.username, "is_admin": user_token.is_admin, "user_id": user_token.user_id}
    elif basic_user:
        return {"username": basic_user.username, "is_admin": basic_user.is_admin}
    else:
        raise HTTPException(status_code=401, detail="Not authenticated")
