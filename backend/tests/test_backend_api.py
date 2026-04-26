from __future__ import annotations

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


def build_client(tmp_path: Path) -> TestClient:
    repo_root = Path(__file__).resolve().parents[2]
    db_copy = tmp_path / "genealogy.sqlite"
    shutil.copyfile(repo_root / "data" / "genealogy.sqlite", db_copy)
    app = create_app(Settings(repo_root=repo_root, db_path=db_copy))
    return TestClient(app)


def test_health(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_search_empty_is_not_error(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    response = client.get("/api/v1/search/persons", params={"q": "不存在的人名"})
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_search_same_name_returns_list(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    response = client.get("/api/v1/search/persons", params={"q": "吴良佐"})
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["items"], list)
    for item in body["items"]:
        assert "father_name" in item
        assert "generation_label" in item


def test_glyph_url_modes(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    db_copy = tmp_path / "genealogy.sqlite"
    shutil.copyfile(repo_root / "data" / "genealogy.sqlite", db_copy)

    local_app = create_app(
        Settings(
            repo_root=repo_root,
            db_path=db_copy,
            read_only=True,
            asset_mode="local",
            workspace_data_root=repo_root / "data",
        )
    )
    local_client = TestClient(local_app)
    local_response = local_client.get("/api/v1/search/persons", params={"q": "泰伯", "limit": 1})
    assert local_response.status_code == 200
    assert local_response.json()["items"][0]["glyph_image_url"].startswith("/assets/glyph_assets/")

    online_app = create_app(
        Settings(
            repo_root=repo_root,
            db_path=db_copy,
            read_only=True,
            asset_mode="online",
            oss_base_url="https://oss.example.test",
        )
    )
    online_client = TestClient(online_app)
    online_response = online_client.get("/api/v1/search/persons", params={"q": "泰伯", "limit": 1})
    assert online_response.status_code == 200
    assert online_response.json()["items"][0]["glyph_image_url"].startswith(
        "https://oss.example.test/genealogy-jpg/workspace/data/glyph_assets/"
    )


def test_search_collapses_auto_duplicates_with_same_visible_signature(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    response = client.get("/api/v1/search/persons", params={"q": "茂"})
    assert response.status_code == 200
    items = response.json()["items"]
    matches = [
        item
        for item in items
        if item["name"] == "茂"
        and item["father_name"] == "度爱宗"
        and item["generation_label"] == "第93世"
    ]
    assert len(matches) == 1
    assert matches[0]["person_ref"] != "p_auto_93_10"


def test_biography_unavailable_for_unknown_person(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    response = client.get("/api/v1/persons/historical/not-found/biography")
    assert response.status_code == 404


def test_submission_approve_flow(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    payload = {
        "target_person_ref": "missing-historical-anchor",
        "target_person_source": "historical",
        "submitter_name": "测试用户",
        "submitter_contact": "wechat:test",
        "new_person": {
            "display_name": "吴新枝",
            "gender": "female",
            "birth_date": "1996-08-12",
            "death_date": None,
            "surname": "吴",
            "living_status": "living",
            "education": "本科",
            "occupation": "教师",
            "bio": "测试续修人物",
        },
        "relation": {"relation_type": "father_daughter"},
        "notes": "测试提交",
    }
    create_response = client.post("/api/v1/submissions", json=payload)
    assert create_response.status_code == 201
    submission_id = create_response.json()["submission_id"]

    list_response = client.get("/api/v1/admin/submissions")
    assert list_response.status_code == 200
    assert any(item["id"] == submission_id for item in list_response.json()["items"])

    approve_response = client.post(
        f"/api/v1/admin/submissions/{submission_id}/approve",
        json={"review_note": "通过"},
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"


def test_branch_endpoint_works_without_modern_data(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    search = client.get("/api/v1/search/persons", params={"q": "吴德文"})
    if not search.json()["items"]:
        return
    first = search.json()["items"][0]
    response = client.get(
        f"/api/v1/persons/{first['person_source']}/{first['person_ref']}/branch",
        params={"up": 2, "down": 2, "include_daughters": True, "include_spouses": True},
    )
    assert response.status_code == 200
    assert "columns" in response.json()


def test_historical_branch_stays_historical_only(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    response = client.get(
        "/api/v1/persons/historical/p_168_005/branch",
        params={"up": 2, "down": 3, "include_daughters": True, "include_spouses": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["focus"]["person_source"] == "historical"
    assert isinstance(body["focus"]["has_modern_extension"], bool)
    for column in body["columns"]:
        for node in column["nodes"]:
            assert node["person_source"] == "historical"
            assert node["node_type"] != "spouse"


def test_historical_route_stays_historical_only(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    response = client.get("/api/v1/persons/historical/p_168_005/route")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["has_modern_extension"], bool)
    for item in body["items"]:
        assert item["person_source"] == "historical"


def test_correction_submission_can_be_created_and_listed(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    payload = {
        "target_person_ref": "p_168_005",
        "target_person_source": "historical",
        "submitter_name": "测试用户",
        "submitter_contact": "wechat:test",
        "field_name": "name",
        "current_value": "永昌",
        "proposed_value": "永长",
        "reason": "疑似录入误差",
        "evidence_note": "家中记忆版本",
    }
    create_response = client.post("/api/v1/corrections", json=payload)
    assert create_response.status_code == 201
    created = create_response.json()
    correction_id = created["correction_id"]
    assert created["status"] == "approved"

    list_response = client.get("/api/v1/admin/corrections")
    assert list_response.status_code == 200
    assert any(
        item["id"] == correction_id
        and item["status"] == "approved"
        and item["resolution_type"] == "apply_as_primary"
        for item in list_response.json()["items"]
    )


def test_correction_submission_updates_primary_name_immediately(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    create_response = client.post(
        "/api/v1/corrections",
        json={
            "target_person_ref": "p_168_005",
            "target_person_source": "historical",
            "submitter_name": "测试用户",
            "submitter_contact": "wechat:test",
            "field_name": "name",
            "current_value": "永昌",
            "proposed_value": "永长",
            "reason": "测试直接更正主名",
            "evidence_note": "测试主名命中",
        },
    )
    assert create_response.status_code == 201
    assert create_response.json()["status"] == "approved"

    search_response = client.get("/api/v1/search/persons", params={"q": "永长"})
    assert search_response.status_code == 200
    items = search_response.json()["items"]
    assert any(
        item["person_ref"].endswith("::p_168_005")
        and item["person_source"] == "historical"
        and item["match_type"] == "primary_exact"
        for item in items
    )
