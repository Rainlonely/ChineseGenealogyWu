from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    repo_root: Path
    db_path: Path
    read_only: bool = False
    allow_direct_corrections: bool = False
    asset_mode: str = "online"
    workspace_data_root: Path | None = None
    oss_base_url: str = ""
    api_title: str = "Wu Genealogy API"
    api_version: str = "v1"

    @property
    def glyph_assets_root(self) -> Path:
        data_root = self.workspace_data_root or (self.repo_root / "data")
        return data_root / "glyph_assets"


@lru_cache()
def get_settings() -> Settings:
    repo_root = Path(__file__).resolve().parents[2]
    db_path = Path(os.getenv("GENEALOGY_DB_PATH", repo_root / "data" / "genealogy.sqlite")).resolve()
    read_only = os.getenv("GENEALOGY_READ_ONLY", "0").strip().lower() in {"1", "true", "yes", "on"}
    allow_direct_corrections = os.getenv("GENEALOGY_ALLOW_DIRECT_CORRECTIONS", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    asset_mode = os.getenv("GENEALOGY_ASSET_MODE", "online").strip().lower()
    if asset_mode not in {"local", "online"}:
        asset_mode = "online"
    workspace_data_root_raw = os.getenv("GENEALOGY_WORKSPACE_DATA_ROOT")
    workspace_data_root = Path(workspace_data_root_raw).expanduser().resolve() if workspace_data_root_raw else None
    oss_base_url = os.getenv("GENEALOGY_OSS_BASE_URL", "").strip()
    return Settings(
        repo_root=repo_root,
        db_path=db_path,
        read_only=read_only,
        allow_direct_corrections=allow_direct_corrections,
        asset_mode=asset_mode,
        workspace_data_root=workspace_data_root,
        oss_base_url=oss_base_url,
    )
