"""Версия из pyproject против того, что уже лежит в PyPI — бид typed-judge-kit-iz1.

Случай 80n: тег v0.2.0 ушёл в индекс, после чего main прожил пять коммитов с кодом,
и всё это время pyproject держал уже занятый номер. Молчали два дня.

Два режима:
    python scripts/version_guard.py              # push в main: версия занята, а код разошёлся с тегом?
    python scripts/version_guard.py --tag v0.2.1 # push тега: имя тега == pyproject.version?

Только stdlib, сети требует лишь первый режим (GET на индекс, без ключей и без записи).
"""
import argparse
import json
import pathlib
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = "typed-judge"
INDEX = f"https://pypi.org/pypi/{PACKAGE}/json"

# что попадает в дистрибутив и меняет поведение установленного пакета.
# ponytail: README.md и tests/ тоже меняют байты sdist, но не поведение — держать их здесь
# значит краснеть на каждом коммите документации между релизами, а такую проверку отключают.
WATCHED = ("src", "pyproject.toml")


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def read_version(rev: str) -> str:
    return tomllib.loads(_git("show", f"{rev}:pyproject.toml"))["project"]["version"]


def fetch_published(timeout: float = 10.0) -> set[str] | None:
    """Версии в индексе, или None — если индекс не ответил (это не то же самое, что «занята»)."""
    try:
        with urllib.request.urlopen(INDEX, timeout=timeout) as r:
            return set(json.load(r)["releases"])
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as e:
        print(f"SKIP: индекс PyPI не ответил ({e.__class__.__name__}: {e}) — версия не проверена")
        return None


def guard_main(rev: str, published: set[str] | None) -> tuple[int, str]:
    version = read_version(rev)
    if published is None:
        return 0, f"SKIP: индекс не прочитан, версия {version} не проверена"
    if version not in published:
        return 0, f"OK: {version} в индексе нет — номер свободен"

    tag = f"v{version}"
    try:
        tag_commit = _git("rev-parse", "--verify", f"{tag}^{{commit}}")
    except subprocess.CalledProcessError:
        return 1, (
            f"ВЕРСИЯ ЗАНЯТА: {version} опубликована в PyPI, но тега {tag} в репозитории нет — "
            f"неясно, что именно опубликовано; поднимите версию в pyproject.toml"
        )

    head = _git("rev-parse", f"{rev}^{{commit}}")
    if head == tag_commit:
        return 0, f"OK: {rev} — это сам тег {tag}"

    changed = _git("diff", "--name-only", tag_commit, head, "--", *WATCHED)
    if not changed:
        return 0, f"OK: {version} опубликована, но {', '.join(WATCHED)} с тега {tag} не менялись"

    files = changed.splitlines()
    return 1, (
        f"ВЕРСИЯ ЗАНЯТА: {version} уже опубликована в PyPI (тег {tag}, {tag_commit[:7]}), "
        f"а с тех пор изменилось {len(files)} файлов пакета:\n  "
        + "\n  ".join(files[:10])
        + ("\n  ..." if len(files) > 10 else "")
        + f"\nЭтот код под номером {version} пользователям не достанется. Поднимите версию в pyproject.toml."
    )


def guard_tag(rev: str, tag: str) -> tuple[int, str]:
    version = read_version(rev)
    if tag.removeprefix("refs/tags/").removeprefix("v") == version:
        return 0, f"OK: тег {tag} совпадает с pyproject.version {version}"
    return 1, f"ТЕГ НЕ СОВПАДАЕТ: тег {tag}, а в pyproject.version {version} — опубликуется не то, что помечено"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rev", default="HEAD", help="коммит для проверки (по умолчанию HEAD)")
    p.add_argument("--tag", help="режим тега: сверить имя тега с pyproject.version")
    a = p.parse_args()

    code, out = guard_tag(a.rev, a.tag) if a.tag else guard_main(a.rev, fetch_published())
    print(out)
    return code


if __name__ == "__main__":
    sys.exit(main())
