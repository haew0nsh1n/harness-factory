from dataclasses import dataclass

import jwt
from fastapi import HTTPException
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError

from web.api.config import Settings


@dataclass(frozen=True)
class EntraPrincipal:
    tenant_id: str
    subject_id: str


class EntraTokenValidator:
    def __init__(
        self,
        *,
        tenant_id: str,
        client_id: str,
        jwks_url: str,
    ) -> None:
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._jwk_client = PyJWKClient(jwks_url)

    @classmethod
    def from_settings(cls, settings: Settings) -> "EntraTokenValidator":
        if (
            not settings.entra_tenant_id
            or not settings.entra_client_id
            or not settings.entra_jwks_url
        ):
            raise RuntimeError("entra auth is not fully configured")
        return cls(
            tenant_id=settings.entra_tenant_id,
            client_id=settings.entra_client_id,
            jwks_url=settings.entra_jwks_url,
        )

    def validate(self, token: str) -> EntraPrincipal:
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256":
                raise PyJWTError("unsupported signing algorithm")

            signing_key = self._jwk_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._client_id,
                issuer=(
                    f"https://login.microsoftonline.com/"
                    f"{self._tenant_id}/v2.0"
                ),
                options={
                    "require": [
                        "aud",
                        "exp",
                        "iss",
                        "nbf",
                        "oid",
                        "tid",
                    ]
                },
            )
        except PyJWTError as exc:
            raise HTTPException(
                status_code=401, detail="authentication required"
            ) from exc

        tenant_id = claims.get("tid")
        subject_id = claims.get("oid")
        if tenant_id != self._tenant_id or not isinstance(subject_id, str) or not subject_id:
            raise HTTPException(status_code=401, detail="authentication required")

        return EntraPrincipal(tenant_id=tenant_id, subject_id=subject_id)
