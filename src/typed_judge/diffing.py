"""Дифф «черновик ↔ опубликованная версия»: HTER-прокси (difflib, редакционное расстояние по
словам к длине черновика) + эвристический NER-фильтр — отделяет правки стиля от правок фактов.
Кандидатные метки выводятся списком на подтверждение владельцу, в labels.json НЕ пишутся.

Ограничения NER-фильтра (зафиксированы намеренно, без тяжёлых зависимостей — только regex):
- числа/даты/проценты ловятся регэкспом; смена валюты/единиц без цифры — нет;
- имена собственные — эвристика «заглавная буква не в начале предложения»; пропускает переименования
  в начале предложения и в цитатах, ложно помечает акронимы и заголовочный регистр в клише.

Ограничение источника (specific to этому vault): в output/Content/published/*.md обычно лежит
заметка-отчёт о публикации (frontmatter edits/edits_note + краткое описание разными словами), а
НЕ сам опубликованный текст. Диффить черновик с телом такой заметки бессмысленно — это два разных
текста (пересказ вместо поста), difflib даст один гигантский псевдо-edit, а не реальный HTER.
Поэтому реальный дифф считается только если в заметке есть явный раздел «## Опубликованный текст»
с текстом поста; без него отчёт ограничивается human-verified полями edits/edits_note.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

_NUMERIC_RE = re.compile(r"\d")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_WORD_RE = re.compile(r"\S+")
_SOURCE_RE = re.compile(r"`(output/Content/drafts/[^`]+\.md)`")
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.S)
# Заметка о публикации может содержать реальный текст поста отдельным разделом — иначе диффить
# нечего (см. published_report: без раздела дифф не считается, только frontmatter edits/edits_note).
_PUBLISHED_TEXT_RE = re.compile(r"## Опубликованный текст\n(.*?)(?:\n## |\Z)", re.S)


def _strip_frontmatter(text: str) -> tuple[dict[str, str], str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip('"')
    return fm, m.group(2)


def _is_factish_word(word: str, is_sentence_start: bool) -> bool:
    if _NUMERIC_RE.search(word):
        return True
    bare = word.strip(".,!?;:«»\"'()")
    return bool(bare) and not is_sentence_start and bare[0].isupper()


def _tag_sentence_starts(text: str) -> list[bool]:
    """True/False по каждому слову текста — является ли оно первым словом предложения."""
    flags: list[bool] = []
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        words = _WORD_RE.findall(sentence)
        flags.extend(i == 0 for i in range(len(words)))
    return flags


@dataclass
class DiffResult:
    hter: float             # редакционное расстояние по словам / длина черновика в словах
    style_edits: int
    fact_edits: int
    fact_examples: list[str]
    candidate: str | None   # "critical" при найденной правке факта, иначе None — только сигнал, не запись

    def to_dict(self) -> dict:
        return {"hter": self.hter, "style_edits": self.style_edits, "fact_edits": self.fact_edits,
                "fact_examples": self.fact_examples, "candidate": self.candidate}


def diff_texts(draft: str, published: str) -> DiffResult:
    a, b = _WORD_RE.findall(draft), _WORD_RE.findall(published)
    a_starts, b_starts = _tag_sentence_starts(draft), _tag_sentence_starts(published)
    sm = SequenceMatcher(a=a, b=b, autojunk=False)

    style_edits = fact_edits = edited_words = 0
    fact_examples: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        span_words = a[i1:i2] + b[j1:j2]
        span_flags = a_starts[i1:i2] + b_starts[j1:j2]
        is_fact = any(_is_factish_word(w, s) for w, s in zip(span_words, span_flags))
        edited_words += max(i2 - i1, j2 - j1)
        if is_fact:
            fact_edits += 1
            fact_examples.append(" ".join(a[i1:i2]) + " → " + " ".join(b[j1:j2]))
        else:
            style_edits += 1

    hter = edited_words / len(a) if a else (0.0 if not b else 1.0)
    candidate = "critical" if fact_edits else None
    return DiffResult(hter=hter, style_edits=style_edits, fact_edits=fact_edits,
                       fact_examples=fact_examples, candidate=candidate)


@dataclass
class PublishedPost:
    path: Path
    edits: str | None
    edits_note: str | None
    source_draft: Path | None
    source_found: bool
    published_text_found: bool
    diff: DiffResult | None


def _is_post_note(fm: dict[str, str]) -> bool:
    # README.md и подобные индексные заметки в published/ без frontmatter — не посты.
    return bool(fm)


def _find_published_posts(vault_root: Path) -> list[PublishedPost]:
    published_dir = vault_root / "output" / "Content" / "published"
    out: list[PublishedPost] = []
    for path in sorted(published_dir.glob("*.md")):
        fm, body = _strip_frontmatter(path.read_text(encoding="utf-8"))
        if not _is_post_note(fm):
            continue
        m = _SOURCE_RE.search(body)
        source_draft = vault_root / m.group(1) if m else None
        source_found = bool(source_draft and source_draft.exists())
        pub_m = _PUBLISHED_TEXT_RE.search(body)
        diff = None
        if source_found and pub_m:
            _, draft_body = _strip_frontmatter(source_draft.read_text(encoding="utf-8"))
            diff = diff_texts(draft_body, pub_m.group(1).strip())
        out.append(PublishedPost(path=path, edits=fm.get("edits"), edits_note=fm.get("edits_note"),
                                  source_draft=source_draft, source_found=source_found,
                                  published_text_found=bool(pub_m), diff=diff))
    return out


def published_report(vault_root: Path) -> str:
    posts = _find_published_posts(Path(vault_root))
    if not posts:
        return f"published-постов не найдено (искал в {vault_root / 'output' / 'Content' / 'published'})"

    lines = [f"published-постов: {len(posts)}"]
    for p in posts:
        lines.append(f"\n## {p.path.stem}")
        lines.append(f"edits (владелец, frontmatter): {p.edits or '—'}" +
                     (f" — {p.edits_note}" if p.edits_note else ""))
        if not p.source_found:
            lines.append("черновик-источник не найден (ссылка `Источник:` в теле заметки отсутствует или битая)")
            continue
        lines.append(f"источник: {p.source_draft}")
        if not p.published_text_found:
            lines.append("нет отдельного текста опубликованной версии в vault (нет раздела "
                         "«## Опубликованный текст» в заметке) — HTER не считается, только "
                         "human-verified edits/edits_note выше; добавьте раздел, чтобы включить дифф")
            continue
        d = p.diff
        lines.append(f"HTER-прокси: {d.hter:.2f}, правок стиль={d.style_edits} факт={d.fact_edits}")
        if d.candidate:
            lines.append(f"кандидат метки (на подтверждение владельцу, в labels.json не записано): {d.candidate}")
            for ex in d.fact_examples:
                lines.append(f"  факт: {ex}")
    return "\n".join(lines)
