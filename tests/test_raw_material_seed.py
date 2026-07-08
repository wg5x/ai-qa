from pathlib import Path
from zipfile import ZipFile

import pytest

from app import database
from app.services.material_search import create_material, is_low_confidence_material, search_materials
from app.services.prompt_builder import build_sales_prompt_context
from app.services.raw_material_seed import (
    build_media_payload,
    extract_docx_paragraphs,
    import_manual_knowledge,
    import_media_directory,
    search_manual_knowledge,
)


def _write_minimal_docx(path: Path, paragraphs: list[str]) -> None:
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(
            f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>" for paragraph in paragraphs
        )
        + "</w:body></w:document>"
    )
    with ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document_xml)


def test_extract_docx_paragraphs_reads_manual_text(tmp_path):
    docx_path = tmp_path / "manual.docx"
    _write_minimal_docx(
        docx_path,
        [
            "短",
            "客户关心噪音时，先说明产品经过装车测试。",
            "包装问题要强调 HIQ 彩盒和品牌识别度。",
        ],
    )

    paragraphs = extract_docx_paragraphs(docx_path)

    assert len(paragraphs) == 2
    assert "装车测试" in paragraphs[0]
    assert "HIQ 彩盒" in paragraphs[1]


def test_import_manual_knowledge_creates_searchable_fragments(client, tmp_path):
    docx_path = tmp_path / "manual.docx"
    _write_minimal_docx(
        docx_path,
        [
            "客户关心噪音时，先说明产品经过装车测试，再解释材料配方。",
            "包装问题要强调 HIQ 彩盒和品牌识别度，可搭配包装视频。",
        ],
    )

    with database.SessionLocal() as db:
        result = import_manual_knowledge(db, docx_path)
        matches = search_manual_knowledge(db, "装车测试")

    assert result["created"] == 2
    assert len(matches) == 1
    assert matches[0].material_type == "knowledge"
    assert "装车测试" in (matches[0].description or "")


def test_build_media_payload_marks_hash_files_as_needs_description(tmp_path):
    file_path = tmp_path / "004fa855ba5fec6b69fba870070d7bae.mp4"
    file_path.write_bytes(b"video")

    payload = build_media_payload(file_path, product_type="brake_pad")

    assert payload["material_type"] == "video"
    assert "needs_description" in payload["tags"]
    assert is_low_confidence_material(payload)


def test_build_media_payload_extracts_material_grade_from_filename(tmp_path):
    file_path = tmp_path / "A+半金属.mp4"
    file_path.write_bytes(b"video")

    payload = build_media_payload(file_path, product_type="brake_pad")

    assert payload["material_grade"] == "A+半金属"
    assert "needs_description" not in payload["tags"]
    assert not is_low_confidence_material(payload)


def test_import_media_directory_registers_files_and_counts_low_confidence(client, tmp_path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "A+半金属.mp4").write_bytes(b"video")
    (media_dir / "004fa855ba5fec6b69fba870070d7bae.mp4").write_bytes(b"video")

    with database.SessionLocal() as db:
        result = import_media_directory(db, media_dir)
        materials = search_materials(db, query="半金属")

    assert result["created"] == 2
    assert result["low_confidence"] == 1
    assert [material["name"] for material in materials] == ["A+半金属"]


def test_low_confidence_materials_are_not_prioritized_in_prompt_context(client):
    with database.SessionLocal() as db:
        create_material(
            db,
            build_media_payload(
                Path("/tmp/hash-video.mp4"),
                product_type="brake_pad",
            )
            | {
                "name": "004fa855ba5fec6b69fba870070d7bae.mp4",
                "file_path": "/tmp/hash-video.mp4",
                "scenario": "包装效果",
                "brand": "HIQ",
                "tags": "auto_indexed,brake_pad,needs_description",
            },
        )
        create_material(
            db,
            {
                "name": "HIQ 包装视频",
                "file_path": "/tmp/hiq-packaging.mp4",
                "material_type": "video",
                "product_type": "brake_pad",
                "scenario": "包装效果",
                "brand": "HIQ",
                "description": "HIQ 包装实拍。",
                "tags": "包装,HIQ",
            },
        )

        context = build_sales_prompt_context(db, "客户想看 HIQ 包装效果")

    assert [material["name"] for material in context["materials"]] == ["HIQ 包装视频"]
