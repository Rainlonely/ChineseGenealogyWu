from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    ok: bool
    api_version: str
    db_path: str
    read_only: bool
