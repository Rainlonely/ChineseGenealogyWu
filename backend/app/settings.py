from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    repo_root: Path
    db_path: Path
    api_title: str = "Wu Genealogy API"
    api_version: str = "v1"


@lru_cache()
def get_settings() -> Settings:
    repo_root = Path(__file__).resolve().parents[2]
    db_path = Path(os.getenv("GENEALOGY_DB_PATH", repo_root / "data" / "genealogy.sqlite")).resolve()
    return Settings(repo_root=repo_root, db_path=db_path)
