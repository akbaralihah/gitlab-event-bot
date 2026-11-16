from fastapi import APIRouter

from app import __version__
from app.schemas.common import HealthResponse

router = APIRouter(tags=["Служебное"])


@router.get(
    "/health",
    summary="Проверка работоспособности",
    description="Возвращает `ok` и версию приложения. Подходит для healthcheck в Docker и мониторинге.",
    response_model=HealthResponse,
)
async def health() -> dict:
    return {"status": "ok", "version": __version__}
