from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import build_router
from app.db.connection import init_modern_schema
from app.services.corrections import CorrectionService
from app.services.persons import PersonService
from app.services.submissions import SubmissionService
from app.settings import Settings, get_settings


def create_app(custom_settings: Settings | None = None) -> FastAPI:
    settings = custom_settings or get_settings()
    if not settings.read_only:
        init_modern_schema(settings.db_path)

    app = FastAPI(title=settings.api_title, version=settings.api_version)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    if settings.asset_mode == "local" and settings.glyph_assets_root.exists():
        app.mount(
            "/assets/glyph_assets",
            StaticFiles(directory=str(settings.glyph_assets_root)),
            name="glyph-assets",
        )

    person_service = PersonService(
        settings.db_path,
        asset_mode=settings.asset_mode,
        oss_base_url=settings.oss_base_url,
    )
    submission_service = SubmissionService(settings.db_path)
    correction_service = CorrectionService(settings.db_path)
    app.include_router(build_router(person_service, submission_service, correction_service, settings))
    return app


app = create_app()
