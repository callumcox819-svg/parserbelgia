from aiogram import Router

from .admin import router as admin_router
from .parser_run import router as parser_router
from .settings import router as settings_router
from .start import router as start_router


def setup_routers() -> Router:
    root = Router()
    root.include_router(start_router)
    root.include_router(settings_router)
    root.include_router(parser_router)
    root.include_router(admin_router)
    return root
