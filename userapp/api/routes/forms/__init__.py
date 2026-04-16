from fastapi import APIRouter

from .base import router
from .user_application import router as user_application_router, form_triggers

# Add user_application_router to base router
router.include_router(user_application_router, tags=["User Entry Application"])
