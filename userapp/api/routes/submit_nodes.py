from fastapi import APIRouter, Response, Depends

from userapp.query_parser import get_filter_query_params
from userapp.api.routes.security import check_is_admin, check_is_authenticated, get_user_from_cookie
from userapp.api.util import list_endpoint, get_one_endpoint, create_one_endpoint, delete_one_endpoint
from userapp.db import session_generator
from userapp.core.schemas.submit_node import SubmitNodeTableSchema, SubmitNodeGet, SubmitNodePost, SubmitNodePatch
from userapp.core.models.tables import SubmitNode as SubmitNodeTable
from userapp.core.services.access import actor_id, apply_and_audit
from userapp.core.services.membership import get_live_group

router = APIRouter(
    prefix="/submit_nodes",
    tags=["Submit Nodes"],
    dependencies=[],
    responses={
        404: {
            "description": "Not found"
        }
    }
)

@router.get("")
async def get_submit_nodes(response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator), is_authenticated=Depends(check_is_authenticated)) -> list[SubmitNodeGet]:
    return await list_endpoint(session, SubmitNodeTable, response, filter_query_params, page, page_size)

@router.delete("/{submit_node_id}", status_code=204)
async def delete_submit_node(submit_node_id: int, session=Depends(session_generator), is_admin=Depends(check_is_admin)) -> None:
    await delete_one_endpoint(session, SubmitNodeTable, submit_node_id)

@router.post("", status_code=201)
async def create_submit_node(submit_node: SubmitNodePost, session=Depends(session_generator), is_admin=Depends(check_is_admin)) -> SubmitNodeGet:
    # A deleted group has no members, so a node pointing at one would grant access to no one
    if submit_node.group_id is not None:
        await get_live_group(session, submit_node.group_id)
    return await create_one_endpoint(session, SubmitNodeTable,  submit_node)

@router.put("/{submit_node_id}", status_code=200)
async def update_submit_node(submit_node_id: int, submit_node: SubmitNodePatch, session=Depends(session_generator), is_admin=Depends(check_is_admin), user_token=Depends(get_user_from_cookie)) -> SubmitNodeGet:
    node = await get_one_endpoint(session, SubmitNodeTable, submit_node_id)
    if submit_node.group_id is not None:
        await get_live_group(session, submit_node.group_id)
    # group_id on the entry is the group after the change, so it shows up on that group's log
    await apply_and_audit(
        session, node, submit_node.model_dump(exclude_unset=True), entity="submit_node",
        actor=actor_id(user_token), group_id_after=lambda row: row.group_id,
    )
    await session.refresh(node)
    return node
