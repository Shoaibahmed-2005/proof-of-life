from pydantic import BaseModel


class HealthCheck(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    project_name: str
