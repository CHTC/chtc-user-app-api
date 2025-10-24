from datetime import datetime, timedelta
import os
from typing import Annotated

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from starlette.responses import Response
import bcrypt
from jose import JWTError, jwt

from api.schemas import Login
from api.models import User
from api.db import get_async_session, get_engine

http_bearer = HTTPBearer(auto_error=False)


class TokenData(BaseModel):
    username: str
    is_admin: bool


router = APIRouter(
    prefix=f"/security",
    responses={
        404: {
            "description": "Not found"
        }
    }
)


@router.post("/login")
async def login_user(response: Response, login: Login):

    engine = get_engine()
    async_session = get_async_session(engine)

    # Get the user
    async with async_session() as session:

        user = session.query(User).where(username=login.username).first()

        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        # Check the password matches
        password_is_valid = bcrypt.checkpw(login.password.encode('utf-8'), user.password)

        if password_is_valid:
            response.set_cookie(
                "access_token",
                f"Bearer {await create_user_token(user.username, user.is_admin)}",
                httponly=True,
                samesite="strict"
            )


async def create_user_token(username: str, is_admin: bool):
    return create_access_token({'username': username, 'is_admin': is_admin})


async def get_user_token_from_cookie(token: Annotated[HTTPAuthorizationCredentials, Depends(http_bearer)]):
    """Get the current user from the JWT token in the cookies"""

    # If there wasn't a token include in the request
    if token is None:
        return None

    try:
        payload = jwt.decode(
            token, os.environ["SECRET_KEY"], algorithms=["HS256"]
        )
        username: str = payload.get("username")
        is_admin: bool = payload.get("is_admin", False)
        token_data = TokenData(username=username, is_admin=is_admin)
    except JWTError as e:
        return None

    return token_data


async def is_admin(user_token = Depends(get_user_token_from_cookie)):
    """Dependency to check if the user is an admin"""

    if not user_token.is_admin:
        raise HTTPException(status_code=403, detail="User is not an admin")

    return True


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    """Create a JWT token"""

    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=60 * 8)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, os.environ["SECRET_KEY"], algorithm="HS256"
    )
    return encoded_jwt