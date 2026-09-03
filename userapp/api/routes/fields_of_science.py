from fastapi import APIRouter, Response, Depends

from userapp.query_parser import get_filter_query_params
from userapp.api.routes.security import check_is_authenticated
from userapp.api.util import list_endpoint
from userapp.db import session_generator
from userapp.core.schemas.projects import FieldsOfScienceGet
from userapp.core.models.tables import FieldsOfScience as FieldsOfScienceTable

router = APIRouter(
    prefix="/fields_of_science",
    tags=["Fields of Science"],
    dependencies=[],
    responses={
        404: {
            "description": "Not found"
        }
    }
)


# Static reference data seeded by migration (~1650 rows). The default page_size is
# large enough to return the whole table in one request, since callers populate a
# picker from it; X-Total-Count still reports the true total for anyone paging.
DEFAULT_PAGE_SIZE = 2000


@router.get("")
async def get_fields_of_science(response: Response, page: int = 0, page_size: int = DEFAULT_PAGE_SIZE, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator), is_authenticated=Depends(check_is_authenticated)) -> list[FieldsOfScienceGet]:
    """List the NSF fields of science reference table (read-only lookup)."""
    return await list_endpoint(session, FieldsOfScienceTable, response, filter_query_params, page, page_size, default_order_by=[FieldsOfScienceTable.fos_id])
