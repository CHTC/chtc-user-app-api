import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from starlette.requests import Request
from starlette.responses import Response
from passlib.hash import bcrypt

from userapp.core.schemas.token_permission import TokenPermissionGet, TokenPermissionPost
from userapp.db import session_generator
from userapp.query_parser import get_filter_query_params
from userapp.api.routes.security import check_is_admin, get_user_from_cookie
from userapp.api.util import list_endpoint, delete_one_endpoint, get_one_endpoint, create_one_endpoint, \
    list_select_stmt, route_method_lookup
from userapp.core.schemas.tokens import TokenGet, TokenGetFull, TokenPost, TokenTableSchema
from userapp.core.models.tables import Token, TokenPermission

router = APIRouter(
    prefix="/tokens",
    tags=["Token"],
    dependencies=[Depends(check_is_admin)],
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
    token = await get_one_endpoint(session, Token, token_id)
    token.expires_at = datetime(1970, 1, 1) # Set the token to be expired


@router.get("/{token_id}")
async def get_token(token_id: int, session=Depends(session_generator)) -> TokenGet:
    return await get_one_endpoint(session, Token, token_id)


@router.post("", status_code=201)
async def create_token(token: TokenPost, session=Depends(session_generator), user_token=Depends(get_user_from_cookie)) -> TokenGetFull:

    generated_token = secrets.token_hex(32)
    hashed_token = bcrypt.hash(generated_token)

    db_token = TokenTableSchema(
        **token.model_dump(exclude_unset=True),
        created_by=user_token.user_id,
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

@router.get("/{token_id}/permissions")
async def get_token_permissions(token_id: int, response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator)) -> list[TokenPermissionGet]:
    select_stmt = select(TokenPermission).where(Token.id == token_id)
    return await list_select_stmt(session, select_stmt, Token, response, filter_query_params, page, page_size)

@router.post("/{token_id}/permissions", status_code=201)
async def create_token_permission(request: Request, token_id: int, permission: TokenPermissionPost, session=Depends(session_generator)) -> TokenPermissionGet:

    # Check that the route exists for the permission
    if route_method_lookup(request.app.routes, permission.route, permission.method) is False:
        raise HTTPException(status_code=400, detail=f"Route {permission.route} with method {permission.method} does not exist")

    token_permission_schema = TokenPermissionGet(**permission.model_dump(), token_id=token_id)
    return await create_one_endpoint(session, TokenPermission, token_permission_schema)

@router.delete("/{token_id}/permissions/{permission_id}", status_code=204)
async def delete_token_permission(token_id: int, permission_id: int, session=Depends(session_generator)) -> None:
    await session.execute(
        delete(TokenPermission).where(
            TokenPermission.id == permission_id,
            TokenPermission.token_id == token_id
        )
    )

