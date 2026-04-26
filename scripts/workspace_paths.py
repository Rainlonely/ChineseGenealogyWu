from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKSPACE_DATA_ROOT = (ROOT.parent / "workspace_data").resolve()

# Prefer a repo-external data root. Can be overridden by env var.
WORKSPACE_DATA_ROOT = Path(
    os.environ.get("FGB_WORKSPACE_DATA_ROOT", str(DEFAULT_WORKSPACE_DATA_ROOT))
).expanduser().resolve()

WORKSPACE_GROUPS_ROOT = WORKSPACE_DATA_ROOT / "groups"
WORKSPACE_BRIDGES_ROOT = WORKSPACE_DATA_ROOT / "bridges"
WORKSPACE_GLYPH_ASSETS_ROOT = WORKSPACE_DATA_ROOT / "glyph_assets"
WORKSPACE_TMP_ROOT = WORKSPACE_DATA_ROOT / "tmp"


def group_dir(group_id: str) -> Path:
    """Return the preferred directory for a group-like workspace."""
    workspace_path = WORKSPACE_GROUPS_ROOT / group_id
    return workspace_path if workspace_path.exists() else ROOT / group_id


def group_json_path(group_id: str) -> Path:
    return group_dir(group_id) / "group_template.json"


def iter_group_dirs(pattern: str = "*") -> list[Path]:
    paths: dict[str, Path] = {}
    for base in (ROOT, WORKSPACE_GROUPS_ROOT):
        if not base.exists():
            continue
        for path in sorted(base.glob(pattern)):
            if path.is_dir() or path.is_symlink():
                paths[path.name] = path.resolve()
    return [paths[name] for name in sorted(paths)]


def iter_bio_project_dirs() -> list[Path]:
    return iter_group_dirs("bio_*")


def resolve_repo_asset_path(url_path: str) -> Path:
    """Map app URL paths to repo files, preferring workspace_data assets."""
    raw_path = Path(str(url_path)).expanduser()
    if raw_path.is_absolute():
        for base in (WORKSPACE_DATA_ROOT, DEFAULT_WORKSPACE_DATA_ROOT, ROOT):
            try:
                rel_to_base = raw_path.resolve().relative_to(base)
            except (OSError, ValueError):
                continue
            if base == ROOT:
                return resolve_repo_asset_path(str(rel_to_base))
            return WORKSPACE_DATA_ROOT / rel_to_base

    rel = str(url_path).lstrip("/")
    parts = Path(rel).parts
    if not parts:
        return ROOT

    head = parts[0]
    tail = Path(*parts[1:]) if len(parts) > 1 else Path()
    workspace_candidate: Path | None = None
    if head.startswith(("gen_", "bio_", "pages_jpg_")):
        workspace_candidate = WORKSPACE_GROUPS_ROOT / head / tail
    elif head == "bridges":
        workspace_candidate = WORKSPACE_BRIDGES_ROOT / tail
    elif head == "data" and len(parts) > 1:
        data_head = parts[1]
        data_tail = Path(*parts[2:]) if len(parts) > 2 else Path()
        if data_head == "glyph_assets":
            workspace_candidate = WORKSPACE_GLYPH_ASSETS_ROOT / data_tail
        elif data_head in {"tmp", "tmp_ocr_shared"}:
            workspace_candidate = WORKSPACE_TMP_ROOT / data_head / data_tail

    if workspace_candidate is not None and workspace_candidate.exists():
        return workspace_candidate
    return ROOT / rel
