import re


class SecretDetected(ValueError):
    pass


_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.I),
    re.compile(r"\bAuthorization\s*:\s*Bearer\s+\S{16,}", re.I),
    re.compile(
        r"\b(?:password|passwd|secret|client[_-]?secret|api[_-]?key|"
        r"access[_-]?token|refresh[_-]?token|accountkey|connection[_-]?string)"
        r"\s*[:=]\s*\S{8,}",
        re.I,
    ),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)


def reject_recognizable_secrets(*values: str) -> None:
    if any(pattern.search(value) for value in values for pattern in _SECRET_PATTERNS):
        raise SecretDetected(
            "Recognizable secret material is not allowed in interview content."
        )
