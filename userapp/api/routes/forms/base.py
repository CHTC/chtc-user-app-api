from fastapi import APIRouter, Depends
from starlette.responses import Response

from userapp.api.routes.security import check_is_admin
from userapp.api.util import list_endpoint
from userapp.core.models.tables import BaseForm as BaseFormTable
from userapp.core.schemas.forms import BaseFormGet
from userapp.db import session_generator
from userapp.query_parser import get_filter_query_params

router = APIRouter(
    prefix="/forms",
    tags=["Forms"],
    responses={
        404: {
            "description": "Not found"
        }
    }
)

@router.get("")
async def get_forms(
    response: Response,
    page: int = 0,
    page_size: int = 100,
    filter_query_params=Depends(get_filter_query_params),
    session=Depends(session_generator),
    _=Depends(check_is_admin),
) -> list[BaseFormGet]:
    if not any(value.startswith("order_by.") for _, value in filter_query_params):
        filter_query_params.append(("id", "order_by.desc"))

    return await list_endpoint(
        session,
        BaseFormTable,
        response,
        filter_query_params,
        page,
        page_size,
    )
