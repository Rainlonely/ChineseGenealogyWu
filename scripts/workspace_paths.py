from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Prefer a repo-external data root. Can be overridden by env var.
WORKSPACE_DATA_ROOT = Path(
    os.environ.get("FGB_WORKSPACE_DATA_ROOT", str(ROOT.parent / "workspace_data"))
).expanduser()

