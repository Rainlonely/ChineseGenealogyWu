#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from workspace_paths import ROOT, WORKSPACE_DATA_ROOT


@dataclass(frozen=True)
class MovePlan:
    source: Path
    target: Path
    kind: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Move large data assets outside the repo and replace them with symlinks."
    )
    parser.add_argument(
        "--workspace-data-root",
        type=Path,
        default=WORKSPACE_DATA_ROOT,
        help="External data root (default: sibling workspace_data, or FGB_WORKSPACE_DATA_ROOT).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the move; default is dry-run.",
    )
    return parser


def discover_pdf_moves(data_root: Path) -> list[MovePlan]:
    plans: list[MovePlan] = []
    for pdf in sorted(ROOT.glob("*.pdf")):
        if pdf.is_file() or pdf.is_symlink():
            plans.append(MovePlan(source=pdf, target=data_root / "pdf" / pdf.name, kind="pdf"))
    return plans


def discover_group_moves(data_root: Path) -> list[MovePlan]:
    plans: list[MovePlan] = []
    patterns = ("bio_*", "gen_*", "pages_jpg_*")
    for pattern in patterns:
        for entry in sorted(ROOT.glob(pattern)):
            if entry.is_dir() or entry.is_symlink():
                plans.append(MovePlan(source=entry, target=data_root / "groups" / entry.name, kind="group"))
    return plans


def discover_core_data_moves(data_root: Path) -> list[MovePlan]:
    plans: list[MovePlan] = []
    bridges = ROOT / "bridges"
    if bridges.exists() or bridges.is_symlink():
        plans.append(MovePlan(source=bridges, target=data_root / "bridges", kind="bridges"))

    glyph_assets = ROOT / "data" / "glyph_assets"
    if glyph_assets.exists() or glyph_assets.is_symlink():
        plans.append(MovePlan(source=glyph_assets, target=data_root / "glyph_assets", kind="glyph_assets"))

    sqlite_db = ROOT / "data" / "genealogy.sqlite"
    if sqlite_db.exists() or sqlite_db.is_symlink():
        plans.append(MovePlan(source=sqlite_db, target=data_root / "sqlite" / "genealogy.sqlite", kind="sqlite"))

    for tmp_dir in sorted((ROOT / "data").glob("tmp*")):
        if tmp_dir.is_dir() or tmp_dir.is_symlink():
            plans.append(MovePlan(source=tmp_dir, target=data_root / "tmp" / tmp_dir.name, kind="tmp"))
    return plans


def symlink_target_text(source: Path, target: Path) -> str:
    return os.path.relpath(target, start=source.parent)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def execute_one(plan: MovePlan) -> None:
    source = plan.source
    target = plan.target
    ensure_parent(target)

    if source.is_symlink():
        link_path = source.readlink()
        resolved = (source.parent / link_path).resolve()
        if resolved == target.resolve():
            return
        raise RuntimeError(f"Source is an unexpected symlink: {source} -> {link_path}")

    if source.exists():
        if target.exists() or target.is_symlink():
            raise RuntimeError(f"Target already exists, aborting: {target}")
        shutil.move(str(source), str(target))
    elif not target.exists():
        raise RuntimeError(f"Neither source nor target exists: {source}")

    if source.exists() or source.is_symlink():
        raise RuntimeError(f"Source path still exists after move: {source}")

    source.symlink_to(symlink_target_text(source, target))


def main() -> int:
    args = build_parser().parse_args()
    data_root = args.workspace_data_root.expanduser().resolve()
    plans = (
        discover_pdf_moves(data_root)
        + discover_group_moves(data_root)
        + discover_core_data_moves(data_root)
    )
    plans = sorted(plans, key=lambda item: str(item.source))

    print(f"repo_root={ROOT}")
    print(f"workspace_data_root={data_root}")
    print(f"planned_moves={len(plans)}")
    for plan in plans:
        rel_source = plan.source.relative_to(ROOT)
        print(f"[{plan.kind}] {rel_source} -> {plan.target}")

    if not args.execute:
        print("dry-run only; add --execute to apply")
        return 0

    for plan in plans:
        execute_one(plan)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

