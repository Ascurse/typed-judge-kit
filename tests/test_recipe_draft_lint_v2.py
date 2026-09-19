from typed_judge.questions import Answer
from typed_judge.recipes import draft_lint as dl
from typed_judge.recipes import draft_lint_v2 as v2

READY_BASE = {"hook": Answer(value=3.0), "evidence": Answer(probability=0.9), "tone": Answer(probability=0.9),
              "one_idea": Answer(probability=0.9), "generic_conclusion": Answer(probability=0.1),
              "symmetry": Answer(probability=0.1), "hedging": Answer(probability=0.1)}


def answers(**flags):
    return {**READY_BASE, **{k: Answer(probability=flags.get(k, 0.1)) for k in v2.FLAGS}}


def test_questions_extend_draft_lint_without_changing_it():
    assert set(v2.QUESTIONS) == set(dl.QUESTIONS) | set(v2.FLAGS)
    assert all(v2.QUESTIONS[k] is dl.QUESTIONS[k] for k in dl.QUESTIONS)


def test_clean_ready_stays_ready_with_base_score():
    assert v2.combine(answers()) == dl.combine(answers())
    assert v2.combine(answers())[1] == "ready"


def test_overclaim_at_threshold_demotes_ready_to_light_edit():
    score, verdict = v2.combine(answers(overclaim=0.76))
    assert verdict == "light_edit"
    assert score == dl.combine(answers())[0]
    assert v2.combine(answers(overclaim=0.75))[1] == "ready"


def test_unsourced_and_loose_end_do_not_affect_verdict():
    assert v2.combine(answers(unsourced=0.99, loose_end=0.99))[1] == "ready"


def test_flags_never_touch_heavy_edit():
    a = {**answers(overclaim=0.9), "hook": Answer(value=0.0), "evidence": Answer(probability=0.0)}
    assert v2.combine(a)[1] == dl.combine(a)[1] == "heavy_edit"
