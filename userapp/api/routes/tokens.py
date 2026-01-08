import secrets

from fastapi import APIRouter, Depends
from starlette.responses import Response
from passlib.hash import bcrypt

from userapp.db import session_generator
from userapp.query_parser import get_filter_query_params
from userapp.api.routes.security import check_is_admin,  get_user_from_cookie
from userapp.api.util import list_endpoint, delete_one_endpoint, get_one_endpoint, create_one_endpoint
from userapp.core.schemas.tokens import TokenGet, TokenGetFull, TokenPost, TokenTableSchema
from userapp.core.models.tables import Token


router = APIRouter(
    prefix="/tokens",
    tags=["Token"],
    dependencies=[],
    responses={
        404: {
            "description": "Not found"
        }
    }
)

@router.get("")
async def get_tokens(response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator)) -> list[TokenGet]:
    return await list_endpoint(session, Token, response, filter_query_params, page, page_size)


@router.delete("/{token_id}", status_code=204)
async def delete_token(token_id: int, session=Depends(session_generator)) -> None:
    await delete_one_endpoint(session, Token, token_id)


@router.get("/{token_id}")
async def get_token(token_id: int, session=Depends(session_generator)) -> TokenGet:
    return await get_one_endpoint(session, Token, token_id)


@router.post("", status_code=201)
async def create_token(token: TokenPost, session=Depends(session_generator), user_token=Depends(get_user_from_cookie)) -> TokenGetFull:

    generated_token = secrets.token_hex(32)
    hashed_token = bcrypt.hash(generated_token)

    db_token = TokenTableSchema(
        **token.model_dump(exclude_unset=True),
        created_by=4,
        token=hashed_token
    )

    created_token = await create_one_endpoint(session, Token, db_token)

    return TokenGetFull(
        id=created_token.id,
        created_by=user_token.user_id,
        token=f"{created_token.id}.{generated_token}",
        description=created_token.description,
        created_at=created_token.created_at,
        expires_at=created_token.expires_at
    )
