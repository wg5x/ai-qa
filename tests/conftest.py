from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app import database
from app.main import app


@pytest.fixture
def client(tmp_path) -> Generator[TestClient, None, None]:
    test_database_url = f"sqlite:///{tmp_path / 'test-sales-ai.sqlite3'}"
    database.configure_database(test_database_url)
    with TestClient(app) as test_client:
        yield test_client
