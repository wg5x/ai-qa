from pathlib import Path

from sqlalchemy import inspect, text

from app import database
from app.config import settings


PROJECT_ROOT = Path(__file__).resolve().parents[1]


EXPECTED_COLUMNS = {
    "quote_records": {
        "id",
        "customer_name",
        "country",
        "part_number",
        "replacement_numbers",
        "material_grade",
        "steel_thickness",
        "has_shim",
        "packaging",
        "quantity",
        "unit_price",
        "currency",
        "quote_date",
        "valid_until",
        "remark",
        "source_file",
        "created_at",
    },
    "contract_records": {
        "id",
        "contract_no",
        "customer_name",
        "country",
        "order_date",
        "part_number",
        "material_grade",
        "packaging",
        "quantity",
        "unit_price",
        "currency",
        "delivery_time",
        "payment_terms",
        "remark",
        "source_file",
        "created_at",
    },
    "materials": {
        "id",
        "name",
        "file_path",
        "material_type",
        "product_type",
        "scenario",
        "brand",
        "material_grade",
        "description",
        "recommended_script",
        "tags",
        "created_at",
    },
    "speech_templates": {
        "id",
        "scenario",
        "customer_question",
        "style_notes",
        "standard_reply",
        "forbidden_words",
        "recommended_material_ids",
        "status",
        "source_chat",
        "created_at",
        "confirmed_at",
    },
}


def test_application_startup_creates_domain_tables(client):
    inspector = inspect(database.engine)

    assert set(EXPECTED_COLUMNS).issubset(inspector.get_table_names())
    for table_name, expected_columns in EXPECTED_COLUMNS.items():
        actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
        assert expected_columns.issubset(actual_columns)


def test_speech_template_status_is_constrained(client):
    with database.engine.begin() as connection:
        try:
            connection.execute(
                text(
                    """
                    INSERT INTO speech_templates (scenario, standard_reply, status)
                    VALUES ('quote_follow_up', 'Use approved language.', 'archived')
                    """
                )
            )
        except Exception as exc:
            assert "status" in str(exc).lower() or "check" in str(exc).lower()
        else:
            raise AssertionError("speech_templates.status accepted an invalid value")


def test_default_database_url_is_project_local():
    expected_database_path = PROJECT_ROOT / "data" / "local-sales-ai.sqlite3"

    assert settings.database_url == f"sqlite:///{expected_database_path}"


def test_database_tests_use_temporary_sqlite(client):
    configured_database = Path(database.engine.url.database)
    default_database = PROJECT_ROOT / "data" / "local-sales-ai.sqlite3"

    assert configured_database.name == "test-sales-ai.sqlite3"
    assert configured_database != default_database
    assert configured_database.exists()
