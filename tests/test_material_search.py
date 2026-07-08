from app import database
from app.services.material_search import (
    create_material,
    delete_material,
    list_materials,
    search_materials,
    update_material,
)


def test_create_material_registers_hiq_packaging_asset(client):
    material_data = {
        "name": "HIQ 彩盒包装效果图",
        "file_path": "/Users/sales/materials/hiq-packaging.jpg",
        "material_type": "image",
        "product_type": "brake_pad",
        "scenario": "包装展示",
        "brand": "HIQ",
        "description": "用于向客户展示 HIQ 包装外观和品牌识别。",
        "tags": "包装,HIQ,彩盒",
    }

    with database.SessionLocal() as db:
        material = create_material(db, material_data)

    assert material["id"] is not None
    assert material["name"] == "HIQ 彩盒包装效果图"
    assert material["file_path"] == "/Users/sales/materials/hiq-packaging.jpg"
    assert material["material_type"] == "image"
    assert material["product_type"] == "brake_pad"
    assert material["scenario"] == "包装展示"
    assert material["brand"] == "HIQ"
    assert material["description"] == "用于向客户展示 HIQ 包装外观和品牌识别。"
    assert material["tags"] == "包装,HIQ,彩盒"
    assert "created_at" in material


def test_search_materials_returns_hiq_packaging_for_customer_query(client):
    with database.SessionLocal() as db:
        create_material(
            db,
            {
                "name": "HIQ 包装视频",
                "file_path": "/Users/sales/materials/hiq-packaging.mp4",
                "material_type": "video",
                "product_type": "brake_pad",
                "scenario": "包装效果",
                "brand": "HIQ",
                "description": "HIQ 包装实拍。",
                "tags": "包装,视频",
            },
        )
        create_material(
            db,
            {
                "name": "KD 工厂图",
                "file_path": "/Users/sales/materials/kd-factory.jpg",
                "material_type": "image",
                "product_type": "brake_pad",
                "scenario": "工厂实力",
                "brand": "KD",
                "description": "KD 工厂外观。",
                "tags": "工厂",
            },
        )

        results = search_materials(db, query="客户想看 HIQ 包装效果")

    assert [material["name"] for material in results] == ["HIQ 包装视频"]
    assert results[0]["brand"] == "HIQ"
    assert "包装" in results[0]["scenario"]
    assert results[0]["file_path"] == "/Users/sales/materials/hiq-packaging.mp4"


def test_search_materials_filters_by_tags_and_material_grade(client):
    with database.SessionLocal() as db:
        create_material(
            db,
            {
                "name": "陶瓷材质说明",
                "file_path": "/Users/sales/materials/ceramic.pdf",
                "material_type": "document",
                "product_type": "brake_pad",
                "scenario": "材质解释",
                "brand": "HIQ",
                "material_grade": "Ceramic",
                "description": "陶瓷刹车片材质说明。",
                "tags": "材质,静音,陶瓷",
            },
        )
        create_material(
            db,
            {
                "name": "半金属说明",
                "file_path": "/Users/sales/materials/semi-metallic.pdf",
                "material_type": "document",
                "product_type": "brake_pad",
                "scenario": "材质解释",
                "brand": "HIQ",
                "material_grade": "Semi-metallic",
                "description": "半金属材质说明。",
                "tags": "材质,耐磨",
            },
        )

        results = search_materials(db, tags="静音", material_grade="ceramic")

    assert [material["name"] for material in results] == ["陶瓷材质说明"]


def test_material_crud_routes_return_local_file_path_without_reading_file(client):
    create_response = client.post(
        "/api/materials",
        json={
            "name": "HIQ 包装图",
            "file_path": "/path/that/does/not/need/to/exist.jpg",
            "material_type": "image",
            "product_type": "brake_pad",
            "scenario": "包装展示",
            "brand": "HIQ",
            "description": "只保存本地路径。",
            "recommended_script": "这是 HIQ 包装效果。",
            "tags": "包装,HIQ",
        },
    )

    assert create_response.status_code == 200
    created = create_response.json()
    assert created["file_path"] == "/path/that/does/not/need/to/exist.jpg"

    list_response = client.get("/api/materials")
    assert list_response.status_code == 200
    assert [material["id"] for material in list_response.json()] == [created["id"]]

    search_response = client.get("/api/materials/search", params={"q": "HIQ 包装"})
    assert search_response.status_code == 200
    assert [material["id"] for material in search_response.json()] == [created["id"]]

    update_response = client.patch(
        f"/api/materials/{created['id']}",
        json={"description": "更新后的描述", "tags": "包装,HIQ,新版"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["description"] == "更新后的描述"

    delete_response = client.delete(f"/api/materials/{created['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True}

    with database.SessionLocal() as db:
        assert list_materials(db) == []
        assert delete_material(db, created["id"]) is False
        assert update_material(db, created["id"], {"description": "missing"}) is None
