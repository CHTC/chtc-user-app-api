from fastapi import APIRouter, Response, Depends

from userapp.query_parser import get_filter_query_params
from userapp.api.routes.security import check_is_admin
from userapp.api.util import list_endpoint, create_one_endpoint, update_one_endpoint, delete_one_endpoint
from userapp.db import session_generator
from userapp.core.schemas.submit_node import SubmitNodeTableSchema, SubmitNodeGet, SubmitNodePost, SubmitNodePatch
from userapp.core.models.tables import SubmitNode as SubmitNodeTable

router = APIRouter(
    prefix="/submit_nodes",
    tags=["Submit Nodes"],
    dependencies=[Depends(check_is_admin)],
    responses={
        404: {
            "description": "Not found"
        }
    }
)

@router.get("")
async def get_submit_nodes(response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator)) -> list[SubmitNodeGet]:
    return await list_endpoint(session, SubmitNodeTable, response, filter_query_params, page, page_size)

@router.delete("/{submit_node_id}", status_code=204)
async def delete_submit_node(submit_node_id: int, session=Depends(session_generator)) -> None:
    await delete_one_endpoint(session, SubmitNodeTable, submit_node_id)

@router.post("/{submit_node_id}")
async def create_submit_node(submit_node: SubmitNodePost, session=Depends(session_generator)) -> SubmitNodeGet:
    return await create_one_endpoint(session, SubmitNodeTable,  submit_node)

@router.put("/{submit_node_id}", status_code=200)
async def update_submit_node(submit_node_id: int, submit_node: SubmitNodePatch, session=Depends(session_generator)) -> SubmitNodeGet:
    return await update_one_endpoint(session, SubmitNodeTable, submit_node_id, submit_node)
