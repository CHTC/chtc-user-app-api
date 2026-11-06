from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import or_, select

from userapp.api.routes.security import check_can_view_group, check_is_admin, check_is_user
from userapp.api.util import get_one_endpoint, list_select_stmt
from userapp.core.models.tables import AuditLog, Group, User
from userapp.core.schemas.audit_log import AuditLogGet
from userapp.core.schemas.users import UserGet
from userapp.db import session_generator
from userapp.query_parser import get_filter_query_params

AuditLogGet.model_rebuild(_types_namespace={'UserGet': UserGet})

# Read-only on purpose: the log is append-only, so there is no POST, PUT or DELETE here
router = APIRouter(
    prefix="/audit_log",
    tags=["Audit Log"],
    responses={
        404: {
            "description": "Not found"
        }
    }
)

# Routes that hang off another prefix (for example /groups/{group_id}/...) go on this router, so
# groups.py and routes/__init__.py stay untouched by wave 2
extra_router = APIRouter(
    responses={
        404: {
            "description": "Not found"
        }
    }
)

# id breaks ties between entries written in one transaction (occurred_at is the transaction's now())
_DEFAULT_ORDER = [AuditLog.occurred_at.desc(), AuditLog.id.desc()]


async def _list_log(session, response, where, filter_query_params, page, page_size):
    select_stmt = select(AuditLog)
    if where is not None:
        select_stmt = select_stmt.where(where)
    return await list_select_stmt(
        session, select_stmt, AuditLog, response, filter_query_params, page, page_size,
        default_order_by=_DEFAULT_ORDER,
    )


@router.get("", dependencies=[Depends(check_is_admin)])
async def get_audit_log(
    response: Response,
    page: int = 0,
    page_size: int = 100,
    filter_query_params=Depends(get_filter_query_params),
    session=Depends(session_generator),
) -> list[AuditLogGet]:
    return await _list_log(session, response, None, filter_query_params, page, page_size)


@router.get("/{audit_log_id}", dependencies=[Depends(check_is_admin)])
async def get_audit_log_entry(audit_log_id: int, session=Depends(session_generator)) -> AuditLogGet:
    return await get_one_endpoint(session, AuditLog, audit_log_id)


@extra_router.get("/groups/{group_id}/audit_log", dependencies=[Depends(check_can_view_group)], tags=["Groups"])
async def get_group_audit_log(
    group_id: int,
    response: Response,
    page: int = 0,
    page_size: int = 100,
    filter_query_params=Depends(get_filter_query_params),
    session=Depends(session_generator),
) -> list[AuditLogGet]:
    """Everything that happened to the group, and every time it was added to or removed from another
    group. Deleted groups stay readable: their history is the point."""

    # Not get_live_group: a deleted group still has a log
    if await session.get(Group, group_id) is None:
        raise HTTPException(status_code=404, detail="Group not found")
    where = or_(AuditLog.group_id == group_id, AuditLog.member_group_id == group_id)
    return await _list_log(session, response, where, filter_query_params, page, page_size)


@extra_router.get("/users/{user_id}/audit_log", dependencies=[Depends(check_is_user)], tags=["Users"])
async def get_user_audit_log(
    user_id: int,
    response: Response,
    page: int = 0,
    page_size: int = 100,
    filter_query_params=Depends(get_filter_query_params),
    session=Depends(session_generator),
) -> list[AuditLogGet]:
    """Changes to the user's memberships, and changes the user made themselves"""

    if await session.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    where = or_(AuditLog.member_user_id == user_id, AuditLog.actor_id == user_id)
    return await _list_log(session, response, where, filter_query_params, page, page_size)
