from __future__ import annotations

import re

SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
SHA256_DIGEST_MESSAGE = "must be a lowercase 64 character sha256 hex digest"


def require_sha256_digest(value: str, field: str) -> str:
    if not isinstance(value, str) or not SHA256_HEX_RE.fullmatch(value):
        raise ValueError(f"{field} {SHA256_DIGEST_MESSAGE}")
    return value
