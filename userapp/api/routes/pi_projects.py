# Signed off by Cannon Lock 2025-11-03

from fastapi import APIRouter, Depends, Response

from userapp.db import session_generator
from userapp.query_parser import get_filter_query_params
from userapp.api.routes.security import check_is_admin
from userapp.api.util import list_endpoint
from userapp.core.models.views import PiProjectView as PiProjectViewTable
from userapp.core.schemas.general import PiProjectView as PiProjectViewSchema

router = APIRouter(
    prefix="/pi-projects",
    tags=["PI Projects"],
    dependencies=[Depends(check_is_admin)],
    responses={
        404: {
            "description": "Not found"
        }
    }
)

@router.get("")
async def get_pi_projects(response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator)) -> list[PiProjectViewSchema]:
    return await list_endpoint(session, PiProjectViewTable, response, filter_query_params, page, page_size)
