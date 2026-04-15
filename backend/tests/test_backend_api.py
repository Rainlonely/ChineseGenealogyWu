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
