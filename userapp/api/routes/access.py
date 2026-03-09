from fastapi import APIRouter, Depends
from starlette.responses import Response

from userapp.api.routes.security import check_is_admin
from userapp.api.util import list_endpoint
from userapp.core.models.tables import Access
from userapp.core.schemas.access import AccessGet
from userapp.db import session_generator
from userapp.query_parser import get_filter_query_params

router = APIRouter(
    prefix="/access_logs",
    tags=["Access"],
    dependencies=[Depends(check_is_admin)],
    responses={404: {"description": "Not found"}},
)


@router.get("")
async def get_access_logs(response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator)) -> list[AccessGet]:
    return await list_endpoint(session, Access, response, filter_query_params, page, page_size)
