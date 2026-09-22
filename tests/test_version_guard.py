"""Проверка «версия уже опубликована, а работа идёт дальше» — бид typed-judge-kit-iz1.

Тест гоняется по настоящей истории репозитория: 6c00ab3 и e58312f — постоянные коммиты,
именно они и есть случай 80n. Набор опубликованных версий подставляется, сеть не идёт.
"""
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

from version_guard import guard_main, guard_tag

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _has(rev: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"],
        capture_output=True,
        check=False,
    ).returncode == 0


needs_history = pytest.mark.skipif(
    not (_has("v0.2.0") and _has("e58312f") and _has("6c00ab3")),
    reason="нужна полная история с тегами (checkout с fetch-depth: 0)",
)


@needs_history
def test_work_under_published_version_fails():
    # e58312f: pyproject 0.2.0, в индексе 0.2.0 от 6c00ab3, между ними 16 файлов src/ — это и был 80n
    code, out = guard_main("e58312f", {"0.2.0"})
    assert code != 0
    assert "0.2.0" in out


@needs_history
def test_head_on_published_tag_passes():
    code, out = guard_main("6c00ab3", {"0.2.0"})
    assert code == 0, out


@needs_history
def test_docs_on_top_of_tag_pass():
    # между v0.2.1 и HEAD только CHANGELOG.md: дистрибутив тот же, шуметь не на чем (предрегистрация в биде)
    code, out = guard_main("HEAD", {"0.2.1"})
    assert code == 0, out


@needs_history
def test_unpublished_version_passes():
    code, out = guard_main("HEAD", {"0.1.0", "0.2.0"})
    assert code == 0, out


def test_unreachable_index_does_not_fail_and_is_named_separately():
    code, out = guard_main("HEAD", None)
    assert code == 0
    assert "SKIP" in out
    assert "занята" not in out


@needs_history
def test_tag_name_must_match_pyproject_version():
    assert guard_tag("6c00ab3", "v0.2.0")[0] == 0
    code, out = guard_tag("6c00ab3", "v0.9.9")
    assert code != 0
    assert "v0.9.9" in out and "0.2.0" in out
