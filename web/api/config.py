from functools import lru_cache
from pathlib import Path
from typing import Literal

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
