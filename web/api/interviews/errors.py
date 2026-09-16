from typing import Literal


InterviewModelErrorCode = Literal[
    "llm_not_configured",
    "llm_auth_unavailable",
    "llm_throttled",
    "llm_timeout",
    "llm_refused",
    "llm_invalid_result",
    "llm_context_limit",
]


class InterviewModelError(RuntimeError):
    def __init__(self, code: InterviewModelErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)
