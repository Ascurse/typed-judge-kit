"""Один вызов движка на item со всеми вопросами; результаты кэшируются в jsonl по ключу (движок, state, вопросы)."""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import time
from dataclasses import asdict, dataclass, field, replace

from .engines import Engine
from .questions import Answer, Choice, Question, Score, question_kind


def question_spec(questions: dict[str, Question]) -> dict:
    spec = {}
    for qid, q in questions.items():
        d = {"type": question_kind(q), "instructions": q.instructions}
        if isinstance(q, Choice):
            d["options"] = q.options
        elif isinstance(q, Score):
            d["anchors"] = list(q.anchors)
        spec[qid] = d
    return spec


def cache_key(engine_name: str, state: str, questions: dict[str, Question]) -> str:
    blob = json.dumps([engine_name, state, question_spec(questions)], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


@dataclass
class Row:
    item_id: str
    key: str
    engine: str
    answers: dict[str, Answer] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["answers"] = {k: a.to_dict() for k, a in self.answers.items()}
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Row":
        d = dict(d)
        d["answers"] = {k: Answer.from_dict(a) for k, a in d["answers"].items()}
        return cls(**d)


def read_rows(path: pathlib.Path) -> list[Row]:
    if not path.exists():
        return []
    rows = []
    # обрыв записи оставляет неполный utf-8 (errors="replace"); splitlines() резал бы валидные строки по U+2028 и т. п.
    for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").split("\n"), 1):
        if not line.strip():
            continue
        try:
            rows.append(Row.from_dict(json.loads(line)))
        except (ValueError, KeyError, TypeError, AttributeError) as e:  # ValueError покрывает JSONDecodeError
            print(f"кэш {path}: строка {n} не разобрана, пропущена ({type(e).__name__}: {e})", file=sys.stderr)
    return rows


def _tail_is_unterminated(path: pathlib.Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    with path.open("rb") as f:
        f.seek(-1, 2)
        return f.read(1) != b"\n"


def append_cache(cache_path: pathlib.Path, new: list[Row]) -> None:
    if not (cache_path and new):
        return
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("a", encoding="utf-8") as f:
        if _tail_is_unterminated(cache_path):  # оборванная запись: без \n первая новая строка склеилась бы с обрывком
            f.write("\n")
        for row in new:
            f.write(json.dumps(row.to_dict(), ensure_ascii=False) + "\n")


def run(engine: Engine, items: dict[str, str], questions: dict[str, Question],
        cache_path: pathlib.Path | None) -> list[Row]:
    cached = {r.key: r for r in read_rows(cache_path) if not r.error} if cache_path else {}
    out: list[Row] = []
    new: list[Row] = []
    for item_id, state in items.items():
        key = cache_key(engine.name, state, questions)
        if key in cached and not cached[key].error:
            out.append(replace(cached[key], item_id=item_id))
            continue
        t0 = time.monotonic()
        try:
            res = engine.ask(state, questions)
            row = Row(item_id, key, engine.name, res.answers, res.input_tokens, res.output_tokens,
                      res.latency_s or time.monotonic() - t0, res.error)
        except Exception as e:  # noqa: BLE001 — ошибка движка становится строкой, не падением прогона
            row = Row(item_id, key, engine.name, {}, 0, 0, time.monotonic() - t0, str(e))
        out.append(row)
        if not row.error:  # ошибка движка не кэшируется, иначе сбой станет постоянным
            new.append(row)
    append_cache(cache_path, new)
    return out
