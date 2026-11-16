from pydantic import BaseModel, Field


class StatusResponse(BaseModel):
    status: str = Field(description="Результат обработки", examples=["sent"])


class HealthResponse(BaseModel):
    status: str = Field(description="Всегда `ok`, если сервис запущен", examples=["ok"])
    version: str = Field(description="Версия приложения", examples=["2.0.0"])


class ErrorResponse(BaseModel):
    detail: str = Field(description="Описание ошибки")
