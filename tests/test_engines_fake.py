import pytest

from typed_judge.engines import load_key, mask
from typed_judge.engines.fake import FakeEngine
from typed_judge.questions import Choice, Noul, Score

Q = {
    "hook": Score("хук?", ("нет", "слабый", "рабочий", "сильный")),
    "evidence": Noul("есть факты"),
    "readiness": Choice("куда?", {"ready": None, "light_edit": None}),
}


def test_fake_is_deterministic_and_counts():
    e = FakeEngine()
    r1 = e.ask("текст", Q)
    r2 = e.ask("текст", Q)
    assert e.calls == 2
    assert r1.answers == r2.answers
    assert 0 <= r1.answers["evidence"].probability < 1
    assert 0 <= r1.answers["hook"].value <= 3
    assert r1.answers["readiness"].value in ("ready", "light_edit")
    assert r1.answers["readiness"].confidence == 0.9


def test_fake_differs_by_state():
    e = FakeEngine()
    assert e.ask("a", Q).answers["evidence"] != e.ask("b", Q).answers["evidence"]


def test_mask_and_load_key(monkeypatch, tmp_path):
    assert mask("sk-abcdef1234") == "...1234"
    monkeypatch.delenv("X_KEY", raising=False)
    with pytest.raises(SystemExit) as ex:
        load_key(("X_KEY",), env_file=tmp_path / "nope")
    assert "X_KEY" in str(ex.value) and "abcdef" not in str(ex.value)
    (tmp_path / ".env").write_text('X_KEY="v-9999"\n')
    assert load_key(("X_KEY",), env_file=tmp_path / ".env") == "v-9999"
