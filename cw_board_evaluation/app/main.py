"""
app.main
--------
FastAPI entrypoint for the C&W Board Evaluation Platform.

Run:
    uvicorn app.main:app --reload

Database schema is not created at startup. Apply migrations first:
    alembic upgrade head
"""

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=False)

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps.auth import require_consultant
from app.api.reports import router as reports_router
from app.api.evaluations import router as evaluations_router
from app.api.questions import router as questions_router
from app.api.portal import router as portal_router
from app.api.assignments import router as assignments_router

try:
    from app.api.debug import router as debug_router
except Exception:
    debug_router = None


def create_app() -> FastAPI:
    app = FastAPI(
        title="Crest & Waterfalls Board Evaluation API",
        version="0.2.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    consultant_auth = [Depends(require_consultant)]

    app.include_router(reports_router, prefix="/api/v1", tags=["reports"], dependencies=consultant_auth)
    app.include_router(evaluations_router, prefix="/api/v1", tags=["evaluations"], dependencies=consultant_auth)
    app.include_router(questions_router, prefix="/api/v1", tags=["questions"], dependencies=consultant_auth)
    app.include_router(portal_router, prefix="/api/v1", tags=["portal"])
    app.include_router(assignments_router, prefix="/api/v1", tags=["assignments"], dependencies=consultant_auth)

    if debug_router is not None:
        app.include_router(debug_router, prefix="/api/v1", tags=["debug"], dependencies=consultant_auth)

    @app.get("/health", tags=["system"])
    async def health():
        return {"status": "ok"}

    print("\n[ROUTES REGISTERED]")
    for r in app.routes:
        methods = getattr(r, "methods", None)
        path = getattr(r, "path", None)
        name = getattr(r, "name", None)
        if path:
            print(f" - {path} | {methods} | {name}")
    print("[/ROUTES REGISTERED]\n")

    return app


app = create_app()
