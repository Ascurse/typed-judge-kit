"""Примитивы вопросов (Choice / Score / Noul) и универсальный Answer — нейтральные к движку."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Choice:
    instructions: str
    options: dict[str, str | None]


@dataclass(frozen=True)
class Score:
    instructions: str
    anchors: tuple[str, ...]

    @property
    def max(self) -> int:
        return len(self.anchors) - 1


@dataclass(frozen=True)
class Noul:
    instructions: str


Question = Choice | Score | Noul


def question_kind(q: Question) -> str:
    return {Choice: "choice", Score: "score", Noul: "noul"}[type(q)]


@dataclass
class Answer:
    value: str | float | None = None
    probability: float | None = None
    confidence: float | None = None
    raw: dict = field(default_factory=dict)
    error: str | None = None

    def numeric(self) -> float | None:
        if self.error:
            return None
        if self.probability is not None:
            return self.probability
        if isinstance(self.value, (int, float)):
            return float(self.value)
        return None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Answer":
        return cls(**d)
