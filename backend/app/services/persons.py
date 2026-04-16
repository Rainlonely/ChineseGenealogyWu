from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from app.repositories.history import HistoryRepository
from app.repositories.modern import ModernRepository


class PersonService:
    def __init__(self, db_path: Path):
        self.history_repo = HistoryRepository(db_path)
        self.modern_repo = ModernRepository(db_path)

    @staticmethod
    def _modern_extension_note(has_modern_extension: bool) -> Optional[str]:
        if not has_modern_extension:
            return None
        return "此支已有现代续修记录"

    @staticmethod
    def _generation_label(generation: Optional[int]) -> str:
        return f"第{generation}世" if generation else "现代续修"

    def _build_route_summary(self, person_source: str, person_ref: str, fallback_name: str) -> str:
        items = self.get_route(person_source, person_ref)["items"]
        names = [item["name"] for item in items[:4]]
        return " / ".join(names) if names else fallback_name

    @staticmethod
    def _is_auto_person_ref(person_ref: str) -> bool:
        return person_ref.startswith("p_auto_")

    def search_persons(self, query: str, limit: int) -> Dict[str, Any]:
        historical_rows = self.history_repo.search_persons(query, limit)
        modern_rows = self.modern_repo.search_persons(query, limit)
        items: List[Dict[str, Any]] = []
        for row in historical_rows:
            items.append(
                {
                    "person_ref": row["id"],
                    "person_source": "historical",
                    "name": row["name"],
                    "father_name": row["father_name"],
                    "generation_label": self._generation_label(row["generation"]),
                    "has_biography": bool(row["has_biography"]),
                    "has_modern_extension": bool(row["has_modern_extension"]),
                    "summary_route": self._build_route_summary("historical", row["id"], row["name"]),
                    "match_reason": "按主名或别名命中",
                    "matched_name": row["matched_name"],
                    "match_type": row["match_type"],
                }
            )
        for row in modern_rows:
            items.append(
                {
                    "person_ref": row["id"],
                    "person_source": "modern",
                    "name": row["display_name"],
                    "father_name": row["father_name"],
                    "generation_label": "现代续修",
                    "has_biography": bool(row["has_biography"]),
                    "has_modern_extension": bool(row["has_modern_extension"]),
                    "summary_route": self._build_route_summary("modern", row["id"], row["display_name"]),
                    "match_reason": "按主名或别名命中",
                    "matched_name": row["matched_name"],
                    "match_type": row["match_type"],
                }
            )
        priority = {
            "primary_exact": 0,
            "alias_exact": 1,
            "primary_fuzzy": 2,
            "alias_fuzzy": 3,
        }
        items.sort(
            key=lambda item: (
                priority[item["match_type"]],
                item["person_source"] != "historical",
                item["name"],
            )
        )
        deduped: Dict[str, Dict[str, Any]] = {}
        for item in items:
            key = f'{item["person_source"]}:{item["person_ref"]}'
            if key not in deduped:
                deduped[key] = item
        items = list(deduped.values())

        collapsed: Dict[str, Dict[str, Any]] = {}
        for item in items:
            signature = "|".join(
                [
                    item["person_source"],
                    item["name"],
                    item.get("father_name") or "",
                    item["generation_label"],
                    item["summary_route"],
                ]
            )
            existing = collapsed.get(signature)
            if not existing:
                collapsed[signature] = item
                continue
            if (
                item["person_source"] == "historical"
                and self._is_auto_person_ref(existing["person_ref"])
                and not self._is_auto_person_ref(item["person_ref"])
            ):
                collapsed[signature] = item

        items = list(collapsed.values())[:limit]
        return {"items": items, "total": len(items)}

    def get_person_detail(self, person_source: str, person_ref: str) -> Dict[str, Any]:
        if person_source == "historical":
            row = self.history_repo.get_person(person_ref)
            if not row:
                raise KeyError(f"Historical person {person_ref} not found")
            biography = self.history_repo.get_best_biography(person_ref)
            return {
                "item": {
                    "person_ref": row["id"],
                    "person_source": "historical",
                    "name": row["name"],
                    "father_name": row["father_name"],
                    "generation_label": self._generation_label(row["generation"]),
                    "source_label": "古籍人物",
                    "has_biography": bool(row["has_biography"]),
                    "has_modern_extension": bool(row["has_modern_extension"]),
                    "modern_extension_note": self._modern_extension_note(bool(row["has_modern_extension"])),
                    "biography_summary": (biography or {}).get("source_text_linear") or (biography or {}).get("source_text_raw"),
                    "actions": {
                        "can_view_biography": bool(row["has_biography"]),
                        "can_view_branch": True,
                        "can_submit_update": True,
                    },
                }
            }

        row = self.modern_repo.get_person(person_ref)
        if not row:
            raise KeyError(f"Modern person {person_ref} not found")
        return {
            "item": {
                "person_ref": row["id"],
                "person_source": "modern",
                "name": row["display_name"],
                "father_name": row["father_name"],
                "generation_label": "现代续修",
                "source_label": "现代续修",
                "has_biography": bool(row.get("bio")),
                "has_modern_extension": bool(row["has_modern_extension"]),
                "modern_extension_note": None,
                "biography_summary": row.get("bio"),
                "actions": {
                    "can_view_biography": bool(row.get("bio")),
                    "can_view_branch": True,
                    "can_submit_update": True,
                },
            }
        }

    def get_biography(self, person_source: str, person_ref: str) -> Dict[str, Any]:
        if person_source == "historical":
            person = self.history_repo.get_person(person_ref)
            if not person:
                raise KeyError(f"Historical person {person_ref} not found")
            biography = self.history_repo.get_best_biography(person_ref)
            if not biography:
                return {"available": False, "source_type": "none"}
            return {
                "available": True,
                "source_type": "historical_biography",
                "title": biography.get("source_title_text"),
                "text_raw": biography.get("source_text_raw"),
                "text_linear": biography.get("source_text_linear"),
                "text_punctuated": biography.get("source_text_punctuated"),
                "text_baihua": biography.get("source_text_baihua"),
            }

        row = self.modern_repo.get_person(person_ref)
        if not row:
            raise KeyError(f"Modern person {person_ref} not found")
        if not row.get("bio"):
            return {"available": False, "source_type": "none"}
        return {
            "available": True,
            "source_type": "modern_bio",
            "title": row["display_name"],
            "text_raw": row["bio"],
            "text_linear": row["bio"],
            "text_punctuated": row["bio"],
            "text_baihua": None,
        }

    def get_route(self, person_source: str, person_ref: str) -> Dict[str, Any]:
        if person_source == "historical":
            person = self.history_repo.get_person(person_ref)
            if not person:
                raise KeyError(f"Historical person {person_ref} not found")
            ancestors = self.history_repo.get_ancestor_chain(person_ref, depth=7)
            items = [
                {
                    "generation": row["generation"],
                    "name": row["name"],
                    "person_ref": row["id"],
                    "person_source": "historical",
                    "note": "父系主链",
                }
                for row in reversed(ancestors[-7:])
            ]
            items.append(
                {
                    "generation": person["generation"],
                    "name": person["name"],
                    "person_ref": person["id"],
                    "person_source": "historical",
                    "note": "当前查看人物",
                }
            )
            return {
                "items": items[-8:],
                "has_modern_extension": bool(person["has_modern_extension"]),
                "modern_extension_note": self._modern_extension_note(bool(person["has_modern_extension"])),
            }

        person = self.modern_repo.get_person(person_ref)
        if not person:
            raise KeyError(f"Modern person {person_ref} not found")
        items: List[Dict[str, Any]] = []
        attachment = self.modern_repo.get_attachment_for_modern(person_ref)
        if attachment:
            anchor_route = self.get_route("historical", attachment["historical_person_ref"])["items"][:-1]
            items.extend(anchor_route)
            items.append(
                {
                    "generation": None,
                    "name": person["display_name"],
                    "person_ref": person["id"],
                    "person_source": "modern",
                    "note": "现代续修人物",
                }
            )
        else:
            items.append(
                {
                    "generation": None,
                    "name": person["display_name"],
                    "person_ref": person["id"],
                    "person_source": "modern",
                    "note": "现代续修人物",
                }
            )
        return {
            "items": items[-8:],
            "has_modern_extension": bool(person["has_modern_extension"]),
            "modern_extension_note": None,
        }

    def get_branch(
        self,
        person_source: str,
        person_ref: str,
        up: int,
        down: int,
        include_daughters: bool,
        include_spouses: bool,
    ) -> Dict[str, Any]:
        columns: List[Dict[str, Any]] = []
        if person_source == "historical":
            person = self.history_repo.get_person(person_ref)
            if not person:
                raise KeyError(f"Historical person {person_ref} not found")
            ancestors = self.history_repo.get_ancestor_chain(person_ref, up)
            descendants = self.history_repo.get_descendant_rows(person_ref, down)
            for row in reversed(ancestors):
                level = row["level"]
                columns.append(
                    {
                        "label": f"上 {level} 代",
                        "generation": row["generation"],
                        "nodes": [
                            {
                                "person_ref": row["id"],
                                "person_source": "historical",
                                "name": row["name"],
                                "relation_to_focus": "父系祖先",
                                "node_type": "ancestor",
                                "relation_type": row["relation_type"],
                            }
                        ],
                    }
                )

            focus_nodes = [
                {
                    "person_ref": person["id"],
                    "person_source": "historical",
                    "name": person["name"],
                    "relation_to_focus": "当前人物",
                    "node_type": "focus",
                    "relation_type": "self",
                }
            ]
            columns.append(
                {
                    "label": "当前人物",
                    "generation": person["generation"],
                    "nodes": focus_nodes,
                }
            )

            for level in range(1, down + 1):
                nodes = [
                    {
                        "person_ref": row["id"],
                        "person_source": "historical",
                        "name": row["name"],
                        "relation_to_focus": f"下 {level} 代",
                        "node_type": "descendant",
                        "relation_type": row["relation_type"],
                    }
                    for row in descendants
                    if row["level"] == level
                ]
                if not nodes:
                    continue
                columns.append(
                    {
                        "label": f"下 {level} 代",
                        "generation": None,
                        "nodes": nodes,
                    }
                )
            return {
                "focus": {
                    "person_ref": person["id"],
                    "person_source": "historical",
                    "name": person["name"],
                    "generation_label": self._generation_label(person["generation"]),
                    "has_modern_extension": bool(person["has_modern_extension"]),
                    "modern_extension_note": self._modern_extension_note(bool(person["has_modern_extension"])),
                },
                "columns": columns,
            }

        person = self.modern_repo.get_person(person_ref)
        if not person:
            raise KeyError(f"Modern person {person_ref} not found")
        focus_nodes = [
            {
                "person_ref": person["id"],
                "person_source": "modern",
                "name": person["display_name"],
                "relation_to_focus": "当前人物",
                "node_type": "focus",
                "relation_type": "self",
            }
        ]
        if include_spouses:
            spouses = self.modern_repo.get_spouses([person_ref], "modern")
            for spouse in spouses:
                focus_nodes.append(
                    {
                        "person_ref": spouse["spouse_person_ref"],
                        "person_source": spouse["spouse_person_source"],
                        "name": spouse["spouse_name"],
                        "relation_to_focus": "配偶",
                        "node_type": "spouse",
                        "relation_type": spouse["relation_type"],
                    }
                )
        columns.append({"label": "当前人物", "generation": None, "nodes": focus_nodes})
        attachment = self.modern_repo.get_attachment_for_modern(person_ref)
        if attachment and up > 0:
            anchor = self.history_repo.get_person(attachment["historical_person_ref"])
            if anchor:
                columns.insert(
                    0,
                    {
                        "label": "上 1 代",
                        "generation": anchor["generation"],
                        "nodes": [
                            {
                                "person_ref": anchor["id"],
                                "person_source": "historical",
                                "name": anchor["name"],
                                "relation_to_focus": "历史挂接点",
                                "node_type": "ancestor",
                                "relation_type": "lineage_attachment",
                            }
                        ],
                    },
                )
        modern_descendants = self.modern_repo.get_descendants_from_roots([person_ref], down)
        for level in range(1, down + 1):
            nodes = []
            for row in modern_descendants:
                if row["level"] != level:
                    continue
                if not include_daughters and "daughter" in row["relation_type"]:
                    continue
                nodes.append(
                    {
                        "person_ref": row["person_id"],
                        "person_source": "modern",
                        "name": row["display_name"],
                        "relation_to_focus": f"下 {level} 代",
                        "node_type": "descendant",
                        "relation_type": row["relation_type"],
                    }
                )
            if nodes:
                columns.append({"label": f"下 {level} 代", "generation": None, "nodes": nodes})
        return {
            "focus": {
                "person_ref": person["id"],
                "person_source": "modern",
                "name": person["display_name"],
                "generation_label": "现代续修",
                "has_modern_extension": bool(person["has_modern_extension"]),
                "modern_extension_note": None,
            },
            "columns": columns,
        }
