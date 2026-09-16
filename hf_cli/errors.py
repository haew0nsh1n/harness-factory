from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CliError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message
