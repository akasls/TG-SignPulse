from fastapi import APIRouter

from backend.api.routes import router as routes_router

router = APIRouter()
router.include_router(routes_router)
