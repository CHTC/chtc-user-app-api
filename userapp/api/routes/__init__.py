from .groups import router as groups_router
from .pi_projects import router as pi_projects_router
from .projects import router as projects_router
from .security import router as security_router
from .submit_nodes import router as submit_nodes_router
from .users import router as users_router
from .tokens import router as tokens_router
from .routes import router as routes_router

all_routers = [
    routes_router,
    groups_router,
    pi_projects_router,
    projects_router,
    security_router,
    submit_nodes_router,
    users_router,
    tokens_router
]
