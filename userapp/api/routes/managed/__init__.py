from fastapi import APIRouter

from .manifest import router as manifest_router
from .morgridge_ad import router as morgridge_ad_router

router = APIRouter(prefix="/managed")
router.include_router(manifest_router)
router.include_router(morgridge_ad_router)

