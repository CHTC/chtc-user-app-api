from fastapi import APIRouter
from fastapi.routing import iter_route_contexts
from starlette.requests import Request

from userapp.core.schemas.routes import RouteGet

router = APIRouter(
    prefix="/routes",
    tags=["Routes"],
    dependencies=[],
    responses={
        404: {
            "description": "Not found"
        }
    }
)

@router.get("")
async def get_routes(requests: Request) -> list[RouteGet]:

    routes: set[tuple[str, str]] = set()
    # app.routes is a tree of included routers; iter_route_contexts walks it
    for r in iter_route_contexts(requests.app.routes):
        for method in r.methods:
            routes.add((r.path, method))

    # Sort by route then method
    routes = sorted(routes, key=lambda x: (x[0], x[1]))

    return [RouteGet(route=path, method=method) for path, method in routes]
