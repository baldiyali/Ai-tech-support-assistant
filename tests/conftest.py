import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    """Tests always exercise the deterministic engine."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(str(tmp_path / "test.db")))


@pytest.fixture
def chat(client):
    state = {"sid": None}

    def send(message, user=None):
        r = client.post("/api/chat", json={"message": message, "session_id": state["sid"], "user": user})
        assert r.status_code == 200, r.text
        data = r.json()
        state["sid"] = data["session_id"]
        return data
    return send
