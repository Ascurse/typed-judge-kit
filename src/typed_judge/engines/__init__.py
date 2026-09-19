"""Протокол движка + общие утилиты ключей. Ключи никогда не печатаются целиком."""
from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass, field
from typing import Protocol

from ..questions import Answer, Question

DEFAULT_ENV_FILE = pathlib.Path.home() / ".hermes/.env"


@dataclass
class Result:
    answers: dict[str, Answer] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0
    error: str | None = None


class Engine(Protocol):
    name: str

    def ask(self, state: str, questions: dict[str, Question]) -> Result: ...


def mask(key: str) -> str:
    return f"...{key[-4:]}"


def load_key(env_names: tuple[str, ...], env_file: pathlib.Path = DEFAULT_ENV_FILE) -> str:
    for n in env_names:
        if os.environ.get(n):
            return os.environ[n]
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            for n in env_names:
                if line.startswith(f"{n}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(f"нет ключа: {' / '.join(env_names)} (env или {env_file})")
