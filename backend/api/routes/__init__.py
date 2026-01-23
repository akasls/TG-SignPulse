from fastapi import APIRouter

from backend.api.routes import accounts, auth, config, events, sign_tasks, tasks, user

router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(user.router, prefix="/user", tags=["user"])
router.include_router(accounts.router, prefix="/accounts", tags=["accounts"])
router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
router.include_router(sign_tasks.router, prefix="/sign-tasks", tags=["sign-tasks"])
router.include_router(config.router, prefix="/config", tags=["config"])
router.include_router(events.router, prefix="/events", tags=["events"])
