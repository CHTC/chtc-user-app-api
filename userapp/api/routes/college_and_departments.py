from fastapi import APIRouter, Response, Depends

from userapp.query_parser import get_filter_query_params
from userapp.api.routes.security import check_is_authenticated
from userapp.api.util import list_endpoint
from userapp.db import session_generator
from userapp.core.schemas.projects import CollegeAndDepartmentGet
from userapp.core.models.tables import CollegeAndDepartment as CollegeAndDepartmentTable

router = APIRouter(
    prefix="/college_and_departments",
    tags=["Colleges and Departments"],
    dependencies=[],
    responses={
        404: {
            "description": "Not found"
        }
    }
)


# Static reference data seeded by migration (~145 rows). The default page_size is
# large enough to return the whole table in one request, since callers populate a
# picker from it; X-Total-Count still reports the true total for anyone paging.
DEFAULT_PAGE_SIZE = 500


@router.get("")
async def get_college_and_departments(response: Response, page: int = 0, page_size: int = DEFAULT_PAGE_SIZE, filter_query_params=Depends(get_filter_query_params), session=Depends(session_generator), is_authenticated=Depends(check_is_authenticated)) -> list[CollegeAndDepartmentGet]:
    """List the college/department reference table (read-only lookup)."""
    return await list_endpoint(session, CollegeAndDepartmentTable, response, filter_query_params, page, page_size, default_order_by=[CollegeAndDepartmentTable.college, CollegeAndDepartmentTable.department])
