from fastapi import APIRouter

from app.core.config import settings
from app.schemas.health import HealthCheck

router = APIRouter()


@router.get("", response_model=HealthCheck)
def get_health() -> HealthCheck:
    """
    Check the health of the application and verify it is running.
    """
    return HealthCheck(
        status="ok",
        version="0.1.0",
        project_name=settings.PROJECT_NAME
    )
