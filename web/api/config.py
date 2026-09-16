from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HF_", extra="forbid")

    database_url: str = "sqlite+pysqlite:///:memory:"
    auth_mode: Literal["development", "entra"] = "development"
    allow_insecure_development_auth: bool = False
    development_organization_id: str = "local-dev"
    development_organization_name: str = "Local Development"
    development_subject_id: str = "portal-dev"
    development_roles: str = "author,reviewer,registry-admin,developer,org-admin"
    artifact_root: Path = Path(".harness-factory/artifacts")
    catalog_root: Path = Path("catalog")
    entra_tenant_id: str | None = None
    entra_client_id: str | None = None
    entra_jwks_url: str | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_deployment: str | None = None
    azure_managed_identity_client_id: str | None = None
    interview_retention_days: int = Field(default=30, ge=1)
    interview_operation_lease_seconds: int = Field(default=75, ge=1)

    @field_validator("azure_openai_endpoint")
    @classmethod
    def validate_azure_openai_endpoint(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlparse(value)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
        ):
            raise ValueError("azure_openai_endpoint must be an HTTPS origin")
        return value.rstrip("/") + "/"


@lru_cache
def get_settings() -> Settings:
    return Settings()
