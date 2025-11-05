# Signed off by Cannon Lock 2025-11-03

from fastapi import APIRouter, Depends, Response

from api.db import session_generator
from api.query_parser import get_filter_query_params
from api.routes.security import is_admin
import api.models as m
import api.schemas as s
from api.util import list_endpoint

router = APIRouter(
    prefix="/pi-projects",
    tags=["PI Projects"],
    dependencies=[Depends(is_admin)],
    responses={
        404: {
            "description": "Not found"
        }
    }
)

@router.get("")
async def get_pi_projects(response: Response, page: int = 0, page_size: int = 100, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator)) -> list[s.PiProjectView]:
    return await list_endpoint(session, m.PiProjectView, s.PiProjectView, response, filter_query_params, page, page_size)
