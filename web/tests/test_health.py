from fastapi.testclient import TestClient

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
