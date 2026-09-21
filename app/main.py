"""Sample API — the service whose contract api-guard protects.

This exists only to give the pipeline something real to check. The interesting
part of the project is what happens to `openapi.yaml` when this file changes.
"""

from fastapi import FastAPI

from app.routers import users

app = FastAPI(
    title="Sample API",
    description="A small user service used to demonstrate API contract testing.",
    version="1.0.0",
)

app.include_router(users.router)


@app.get(
    "/health",
    tags=["ops"],
    summary="Liveness probe",
    responses={200: {"description": "The service is up."}},
)
def health() -> dict[str, str]:
    """Used by the deploy stage to wait for staging to come up."""
    return {"status": "ok"}
