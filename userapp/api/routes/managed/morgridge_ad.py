from userapp.core.models.enum import EntityManagerEnum
from userapp.api.routes.managed._factory import create_managed_router

router = create_managed_router(
    prefix="/morgridge-ad",
    tags=["Morgridge AD Sync"],
    manager=EntityManagerEnum.MORGRIDGE_AD,
)
