from userapp.core.models.enum import EntityManagerEnum
from userapp.api.routes.managed._factory import create_managed_router

router = create_managed_router(
    prefix="/manifest",
    tags=["Manifest Sync"],
    manager=EntityManagerEnum.MANIFEST,
)
