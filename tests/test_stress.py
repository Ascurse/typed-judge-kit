"""Правило «пропуск критического → auto off» и flip-rate RU-пар (bead typed-judge-kit-h37). Без сети — на голых Verdict."""
from typed_judge import stress
from typed_judge.verdict import Verdict


def _v(item_id, verdict, score=0.5):
    return Verdict(item_id, score, verdict)


def test_auto_stays_on_when_no_critical_fixture_gets_ready():
    verdicts = [_v("crit-1", "heavy_edit"), _v("crit-2", "light_edit"), _v("clean-1", "ready")]
    status = stress.auto_status(verdicts, critical_ids={"crit-1", "crit-2"})
    assert status.status == stress.AUTO
    assert status.missed == []


def test_one_missed_critical_turns_auto_off():
    verdicts = [_v("crit-1", "ready"), _v("crit-2", "heavy_edit")]
    status = stress.auto_status(verdicts, critical_ids={"crit-1", "crit-2"})
    assert status.status == stress.OFF
    assert status.missed == ["crit-1"]


def test_auto_off_reports_every_missed_id_not_just_first():
    verdicts = [_v("crit-1", "ready"), _v("crit-2", "ready"), _v("crit-3", "heavy_edit")]
    status = stress.auto_status(verdicts, critical_ids={"crit-1", "crit-2", "crit-3"})
    assert status.status == stress.OFF
    assert set(status.missed) == {"crit-1", "crit-2"}


def test_critical_id_missing_from_verdicts_is_not_a_false_miss():
    """Вердикт мог не посчитаться (ошибка движка) — не в этом списке, но и не пропуск: id просто отсутствует."""
    verdicts = [_v("crit-1", "heavy_edit")]
    status = stress.auto_status(verdicts, critical_ids={"crit-1", "crit-absent"})
    assert status.status == stress.AUTO
    assert status.missed == []


def test_flip_rate_is_zero_when_clean_always_scores_at_least_as_high():
    verdicts = [_v("messy-1", "light_edit", 0.4), _v("clean-1", "ready", 0.8)]
    assert stress.flip_rate([("messy-1", "clean-1")], verdicts) == 0.0


def test_flip_rate_counts_pairs_where_clean_scores_lower_than_messy():
    verdicts = [_v("messy-1", "ready", 0.9), _v("clean-1", "light_edit", 0.5),
                _v("messy-2", "light_edit", 0.4), _v("clean-2", "ready", 0.8)]
    rate = stress.flip_rate([("messy-1", "clean-1"), ("messy-2", "clean-2")], verdicts)
    assert rate == 0.5


def test_flip_rate_ignores_pairs_with_missing_or_unscored_verdict():
    verdicts = [_v("messy-1", "ready", None), _v("clean-1", "ready", 0.8)]
    assert stress.flip_rate([("messy-1", "clean-1"), ("messy-2", "clean-2")], verdicts) == 0.0
