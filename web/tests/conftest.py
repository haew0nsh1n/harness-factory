import io
import json
import urllib.request
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from jwt import encode as jwt_encode
from jwt.algorithms import RSAAlgorithm
from sqlalchemy import text
from cryptography.hazmat.primitives.asymmetric import rsa

from web.api.config import Settings
from web.api.main import create_app
from web.api.db import Base
from web.api.organizations.models import Organization


@pytest.fixture
def development_client() -> Iterator[TestClient]:
    app = create_app(
        Settings(
            auth_mode="development",
            allow_insecure_development_auth=True,
        )
    )
    with TestClient(app) as client:
        yield client


@pytest.fixture
def interview_client_factory():
    clients: list[TestClient] = []

    def build(model):
        app = create_app(
            Settings(
                auth_mode="development",
                allow_insecure_development_auth=True,
                database_url="sqlite+pysqlite:///:memory:",
            ),
            interview_model_factory=lambda settings: model,
        )
        Base.metadata.create_all(app.state.engine)
        with app.state.session_factory.begin() as session:
            session.add(
                Organization(
                    id="org-acme",
                    entra_tenant_id="tenant-acme",
                    name="Acme",
                )
            )
        client = TestClient(app)
        clients.append(client)
        return client, app

    yield build

    for client in clients:
        client.close()


@pytest.fixture
def entra_client() -> Iterator[TestClient]:
    app = create_app(
        Settings(
            auth_mode="entra",
            entra_tenant_id="tenant-123",
            entra_client_id="client-123",
            entra_jwks_url="https://entra.example.test/discovery/keys",
        )
    )
    with TestClient(app) as client:
        yield client


@pytest.fixture
def entra_app():
    app = create_app(
        Settings(
            auth_mode="entra",
            database_url="sqlite+pysqlite:///:memory:",
            entra_tenant_id="tenant-123",
            entra_client_id="client-123",
            entra_jwks_url="https://entra.example.test/discovery/keys",
        )
    )
    with app.state.engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE organizations (
                    id VARCHAR(80) PRIMARY KEY,
                    entra_tenant_id VARCHAR(80) UNIQUE NOT NULL,
                    name VARCHAR(200) NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE memberships (
                    organization_id VARCHAR(80) NOT NULL,
                    subject_id VARCHAR(80) NOT NULL,
                    roles_json JSON NOT NULL,
                    PRIMARY KEY (organization_id, subject_id)
                )
                """
            )
        )
    return app


@pytest.fixture
def seed_identity_data(
    entra_app,
) -> Callable[[list[dict[str, str]], list[dict[str, str]]], None]:
    def seed(
        organizations: list[dict[str, str]], memberships: list[dict[str, str]]
    ) -> None:
        with entra_app.state.engine.begin() as connection:
            for organization in organizations:
                connection.execute(
                    text(
                        """
                        INSERT INTO organizations (id, entra_tenant_id, name)
                        VALUES (:id, :entra_tenant_id, :name)
                        """
                    ),
                    organization,
                )
            for membership in memberships:
                connection.execute(
                    text(
                        """
                        INSERT INTO memberships (
                            organization_id,
                            subject_id,
                            roles_json
                        ) VALUES (
                            :organization_id,
                            :subject_id,
                            :roles_json
                        )
                        """
                    ),
                    {
                        **membership,
                        "roles_json": json.dumps(membership["roles_json"]),
                    },
                )

    return seed


@pytest.fixture
def rsa_private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def stub_entra_jwks(monkeypatch, rsa_private_key) -> None:
    jwk = RSAAlgorithm.to_jwk(rsa_private_key.public_key(), as_dict=True)
    jwk.update({"kid": "test-kid", "alg": "RS256", "use": "sig"})
    payload = json.dumps({"keys": [jwk]}).encode()

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            self.close()
            return False

    def fake_urlopen(request, timeout=30, context=None):
        del timeout, context
        if isinstance(request, urllib.request.Request):
            assert request.full_url == "https://entra.example.test/discovery/keys"
        else:
            assert request == "https://entra.example.test/discovery/keys"
        return Response(payload)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)


@pytest.fixture
def build_entra_token(
    rsa_private_key,
) -> Callable[..., str]:
    def build(
        *,
        tenant_id: str = "tenant-123",
        subject_id: str = "oid-123",
        audience: str = "client-123",
        issuer: str = "https://login.microsoftonline.com/tenant-123/v2.0",
        expires_delta: timedelta = timedelta(minutes=5),
        not_before_delta: timedelta = timedelta(minutes=-1),
        algorithm: str = "RS256",
        key_id: str = "test-kid",
        extra_claims: dict[str, object] | None = None,
    ) -> str:
        now = datetime.now(UTC)
        claims = {
            "aud": audience,
            "iss": issuer,
            "tid": tenant_id,
            "oid": subject_id,
            "exp": now + expires_delta,
            "nbf": now + not_before_delta,
            "iat": now,
        }
        if extra_claims:
            claims.update(extra_claims)

        if algorithm == "RS256":
            return jwt_encode(
                claims,
                rsa_private_key,
                algorithm="RS256",
                headers={"kid": key_id},
            )

        return jwt_encode(
            claims,
            "shared-secret",
            algorithm=algorithm,
            headers={"kid": key_id},
        )

    return build
