import pytest
from fastapi.testclient import TestClient
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "test.sqlite3")
    with TestClient(app) as client:
        yield client
