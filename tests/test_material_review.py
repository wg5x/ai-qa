from app import database
from app.services.material_search import list_materials
from app.services.prompt_builder import build_sales_prompt_context


def test_scan_material_reviews_creates_pending_items_without_materials(client, tmp_path):
    media_dir = tmp_path / "raw"
    media_dir.mkdir()
    (media_dir / "HIQ-普通半金属-包装视频.mp4").write_bytes(b"video")

    response = client.post(
        "/api/material-reviews/scan",
        json={"directory_path": str(media_dir), "product_type": "brake_pad"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["created"] == 1
    assert payload["skipped"] == 0
    assert payload["pending"] == 1

    reviews = client.get("/api/material-reviews").json()
    assert reviews["total"] == 1
    item = reviews["items"][0]
    assert item["status"] == "pending"
    assert item["material_type"] == "video"
    assert item["brand"] == "HIQ"
    assert item["material_grade"] == "普通半金属"
    assert item["scenario"] == "包装展示"
    assert "auto_tagged" in item["tags"]
    assert "video_analysis" in item["tags"]

    with database.SessionLocal() as db:
        assert list_materials(db) == []


def test_confirm_material_review_creates_recommendable_material(client, tmp_path):
    media_dir = tmp_path / "raw"
    media_dir.mkdir()
    file_path = media_dir / "HIQ-普通半金属-包装视频.mp4"
    file_path.write_bytes(b"video")

    client.post(
        "/api/material-reviews/scan",
        json={"directory_path": str(media_dir), "product_type": "brake_pad"},
    )
    review = client.get("/api/material-reviews").json()["items"][0]

    update_response = client.patch(
        f"/api/material-reviews/{review['id']}",
        json={
            "description": "HIQ 普通半金属包装视频，可展示彩盒效果。",
            "recommended_script": "这是 HIQ 包装实拍视频，可以发给客户确认包装效果。",
            "tags": "auto_tagged,video_analysis,包装,HIQ,普通半金属",
        },
    )
    assert update_response.status_code == 200

    confirm_response = client.post(f"/api/material-reviews/{review['id']}/confirm")

    assert confirm_response.status_code == 200
    confirmed = confirm_response.json()
    assert confirmed["status"] == "confirmed"
    assert confirmed["material_id"] is not None

    with database.SessionLocal() as db:
        materials = list_materials(db)
        context = build_sales_prompt_context(db, "客户想看 HIQ 包装视频，怎么回复？")

    assert [material["file_path"] for material in materials] == [str(file_path)]
    assert context["materials"]
    assert context["materials"][0]["brand"] == "HIQ"
    assert context["materials"][0]["material_type"] == "video"


def test_reject_material_review_does_not_create_material(client, tmp_path):
    media_dir = tmp_path / "raw"
    media_dir.mkdir()
    (media_dir / "微信图片_20231211160357.jpg").write_bytes(b"image")

    client.post("/api/material-reviews/scan", json={"directory_path": str(media_dir)})
    review = client.get("/api/material-reviews").json()["items"][0]

    response = client.post(f"/api/material-reviews/{review['id']}/reject")

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    with database.SessionLocal() as db:
        assert list_materials(db) == []


def test_scan_material_reviews_accepts_single_file_path(client, tmp_path):
    file_path = tmp_path / "A+半金属实物图.jpg"
    file_path.write_bytes(b"image")

    response = client.post(
        "/api/material-reviews/scan",
        json={"directory_path": str(file_path), "product_type": "brake_pad"},
    )

    assert response.status_code == 200
    review = client.get("/api/material-reviews").json()["items"][0]
    assert review["material_type"] == "image"
    assert review["material_grade"] == "A+半金属"
    assert review["scenario"] == "材质展示"


def test_analyze_material_path_returns_suggestion_without_creating_review_or_material(client, tmp_path):
    file_path = tmp_path / "HIQ-普通半金属-包装视频.mp4"
    file_path.write_bytes(b"video")

    response = client.post(
        "/api/material-reviews/analyze",
        json={"file_path": str(file_path), "product_type": "brake_pad"},
    )

    assert response.status_code == 200
    suggestion = response.json()
    assert suggestion["file_path"] == str(file_path)
    assert suggestion["material_type"] == "video"
    assert suggestion["brand"] == "HIQ"
    assert suggestion["material_grade"] == "普通半金属"
    assert suggestion["scenario"] == "包装展示"
    assert "video_analysis" in suggestion["tags"]

    assert client.get("/api/material-reviews").json()["total"] == 0
    with database.SessionLocal() as db:
        assert list_materials(db) == []


def test_upload_then_analyze_and_save_material(client):
    upload_response = client.post(
        "/api/materials/upload",
        files={"file": ("HIQ-普通半金属-包装视频.mp4", b"video", "video/mp4")},
    )

    assert upload_response.status_code == 200
    file_path = upload_response.json()["file_path"]

    analyze_response = client.post(
        "/api/material-reviews/analyze",
        json={"file_path": file_path, "product_type": "brake_pad"},
    )

    assert analyze_response.status_code == 200
    suggestion = analyze_response.json()
    assert suggestion["brand"] == "HIQ"
    assert suggestion["material_grade"] == "普通半金属"

    save_response = client.post(
        "/api/materials",
        json=suggestion | {"description": "人工确认后的描述"},
    )

    assert save_response.status_code == 200
    assert save_response.json()["file_path"] == file_path
    assert save_response.json()["description"] == "人工确认后的描述"
