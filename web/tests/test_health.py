from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, Mock

from web.api.config import Settings
from web.api.main import create_app


def test_health_reports_service_without_database_details():
    app = create_app(
        Settings(auth_mode="development", allow_insecure_development_auth=True)
    )

    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "service": "harness-factory-web",
        "version": "1.1.0",
    }


def test_application_lifespan_closes_shared_interview_model():
    model = Mock()
    model.close = AsyncMock()
    app = create_app(
        Settings(auth_mode="development", allow_insecure_development_auth=True),
        interview_model_factory=Mock(return_value=model),
    )

    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert app.state.interview_model is model

    model.close.assert_awaited_once_with()
