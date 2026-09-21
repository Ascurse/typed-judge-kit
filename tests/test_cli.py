import json

from typed_judge import report as report_mod
from typed_judge.batch import Row
from typed_judge.cli import main
from typed_judge.verdict import Verdict


def write_drafts(tmp_path, n=2):
    paths = []
    for i in range(n):
        p = tmp_path / f"draft-{i}.md"
        p.write_text(f"---\ntitle: x\n---\nЧерновик номер {i}. За 3 месяца R@5 вырос с 13% до 93%.", encoding="utf-8")
        paths.append(str(p))
    return paths


def test_run_then_rerun_uses_cache(tmp_path, capsys):
    paths = write_drafts(tmp_path)
    cache = tmp_path / "r.jsonl"
    code = main(["run", "--recipe", "typed_judge.recipes.draft_lint", "--engine", "fake", "--cache", str(cache), *paths])
    out = capsys.readouterr().out
    assert code in (0, 1) and "| draft-0 |" in out and "| draft-1 |" in out
    assert len(cache.read_text().splitlines()) == 2
    main(["run", "--recipe", "typed_judge.recipes.draft_lint", "--engine", "fake", "--cache", str(cache), *paths])
    assert len(cache.read_text().splitlines()) == 2  # ни одной новой строки
    assert (tmp_path / "verdicts.jsonl").exists()


def test_calibrate_prints_agreement_and_certification_impossible(tmp_path, capsys):
    paths = write_drafts(tmp_path)
    cache = tmp_path / "r.jsonl"
    main(["run", "--recipe", "typed_judge.recipes.draft_lint", "--engine", "fake", "--cache", str(cache), *paths])
    (tmp_path / "labels.json").write_text(json.dumps({"labels": {"draft-0": "ready", "draft-1": "light_edit"}}))
    code = main(["calibrate", "--recipe", "typed_judge.recipes.draft_lint", "--cache", str(cache),
                 "--labels", str(tmp_path / "labels.json"), "--out", str(tmp_path / "t.json")])
    out = capsys.readouterr().out
    assert code == 0 and "согласие вердикта с метками" in out and "/2" in out
    assert "сертификация невозможна, auto off" in out and "auto выключен" in out
    assert json.loads((tmp_path / "t.json").read_text())["n"] == 2


def test_calibrate_holdout_ids_excluded_from_calibration(tmp_path, capsys):
    paths = write_drafts(tmp_path)
    cache = tmp_path / "r.jsonl"
    main(["run", "--recipe", "typed_judge.recipes.draft_lint", "--engine", "fake", "--cache", str(cache), *paths])
    (tmp_path / "labels.json").write_text(json.dumps({
        "holdout": ["draft-0"],
        "labels": {"draft-0": "ready", "draft-1": "light_edit"},
    }))
    code = main(["calibrate", "--recipe", "typed_judge.recipes.draft_lint", "--cache", str(cache),
                 "--labels", str(tmp_path / "labels.json"), "--out", str(tmp_path / "t.json")])
    out = capsys.readouterr().out
    assert code == 0 and "holdout" in out and "не участвует в подборе порога" in out
    assert json.loads((tmp_path / "t.json").read_text())["n"] == 1


def test_calibrate_reads_mqm_dict_labels_backward_compatibly(tmp_path, capsys):
    paths = write_drafts(tmp_path)
    cache = tmp_path / "r.jsonl"
    main(["run", "--recipe", "typed_judge.recipes.draft_lint", "--engine", "fake", "--cache", str(cache), *paths])
    (tmp_path / "labels.json").write_text(json.dumps({
        "labels": {"draft-0": "ready", "draft-1": {"verdict": "light_edit", "category": "minor"}},
    }))
    code = main(["calibrate", "--recipe", "typed_judge.recipes.draft_lint", "--cache", str(cache),
                 "--labels", str(tmp_path / "labels.json")])
    out = capsys.readouterr().out
    assert code == 0 and "согласие вердикта с метками" in out and "/2" in out


def test_calibrate_prints_kappa_from_retest_pairs_in_labels_json(tmp_path, capsys):
    paths = write_drafts(tmp_path)
    cache = tmp_path / "r.jsonl"
    main(["run", "--recipe", "typed_judge.recipes.draft_lint", "--engine", "fake", "--cache", str(cache), *paths])
    (tmp_path / "labels.json").write_text(json.dumps({
        "labels": {"draft-0": "ready", "draft-1": "light_edit"},
        "retest_pairs": [{"id": "x", "first": "ready", "retest": "ready"}],
    }))
    code = main(["calibrate", "--recipe", "typed_judge.recipes.draft_lint", "--cache", str(cache),
                 "--labels", str(tmp_path / "labels.json")])
    out = capsys.readouterr().out
    assert code == 0 and "каппа Коэна" in out and "n=1" in out


def test_variants_table(tmp_path, capsys):
    (path,) = write_drafts(tmp_path, 1)
    code = main(["variants", "--recipe", "typed_judge.recipes.draft_lint", "--engine", "fake",
                 "--cache", str(tmp_path / "r.jsonl"), path])
    out = capsys.readouterr().out
    assert code == 0 and "| factor |" in out and "| holistic |" in out and "| factor_en |" in out


def test_diff_published_reports_no_posts_found(tmp_path, capsys):
    (tmp_path / "output" / "Content" / "published").mkdir(parents=True)
    code = main(["diff-published", "--vault-root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0 and "published-постов не найдено" in out


def test_report_compare(tmp_path, capsys):
    paths = write_drafts(tmp_path)
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    main(["run", "--recipe", "typed_judge.recipes.draft_lint", "--engine", "fake", "--cache", str(a), *paths])
    main(["run", "--recipe", "typed_judge.recipes.draft_lint", "--engine", "fake", "--cache", str(b), *paths])
    code = main(["report", "--recipe", "typed_judge.recipes.draft_lint", "--compare", str(a), str(b)])
    out = capsys.readouterr().out
    assert code == 0 and "совпало 2/2" in out


def test_unknown_engine_exits_2():
    assert main(["run", "--recipe", "typed_judge.recipes.draft_lint", "--engine", "nope", "--cache", "x.jsonl", "f.md"]) == 2


def test_argparse_error_has_no_stray_exit_code_line(capsys):
    assert main(["report"]) == 2
    err = capsys.readouterr().err.strip().splitlines()
    assert err and err[-1] != "2"


def test_report_without_cache_or_compare_exits_2():
    assert main(["report", "--recipe", "typed_judge.recipes.draft_lint"]) == 2


def test_bad_recipe_exits_2():
    assert main(["run", "--recipe", "typed_judge.recipes.nope", "--engine", "fake", "--cache", "x.jsonl", "f.md"]) == 2


def test_missing_input_file_exits_2(tmp_path):
    code = main(["run", "--recipe", "typed_judge.recipes.draft_lint", "--engine", "fake",
                 "--cache", str(tmp_path / "r.jsonl"), str(tmp_path / "nope.md")])
    assert code == 2


def test_markdown_escapes_pipe_and_newline():
    row = Row(item_id="x", key="k", engine="fake", error="HTTP 500: a|b\nc")
    verdict = Verdict("x", None, "human", error="HTTP 500: a|b\nc")
    out = report_mod.markdown([row], [verdict])
    assert "a\\|b c" in out
    assert len(out.splitlines()) == 5  # перенос строки в ошибке не должен разорвать таблицу


def test_engine_failure_exits_1(tmp_path, monkeypatch):
    (path,) = write_drafts(tmp_path, 1)

    class Boom:
        name = "boom"

        def ask(self, s, q):
            raise RuntimeError("x")

    monkeypatch.setattr("typed_judge.cli.make_engine", lambda name: Boom())
    code = main(["run", "--recipe", "typed_judge.recipes.draft_lint", "--engine", "fake",
                 "--cache", str(tmp_path / "r.jsonl"), path])
    assert code == 1


# --- шаг claim-vs-evidence из CLI: tj run --sources DIR (бид typed-judge-kit-x5r) ---

V3 = "typed_judge.recipes.draft_lint_v3"


class ClaimStubEngine:
    """Чистый черновик по вопросам рецепта; целостный claim-вопрос срабатывает, если источник спорит."""

    name = "fake"

    def __init__(self):
        self.calls = 0

    def ask(self, state, questions):
        from typed_judge.engines import Result
        from typed_judge.questions import Answer, Choice, Noul
        self.calls += 1
        out = {}
        for qid, q in questions.items():
            if isinstance(q, Choice):
                out[qid] = Answer(value=list(q.options)[0], confidence=0.9)
            elif isinstance(q, Noul):
                fires = qid == "any_unsupported" and "ошибся 30 раз" in state
                out[qid] = Answer(probability=0.9 if fires else 0.1)
        return Result(answers=out)


def write_pair(tmp_path, draft_text, source_text=None):
    (tmp_path / "src").mkdir(exist_ok=True)
    p = tmp_path / "d.md"
    p.write_text(draft_text, encoding="utf-8")
    if source_text is not None:
        (tmp_path / "src" / "d.md").write_text(source_text, encoding="utf-8")
    return str(p)


def run_v3(tmp_path, monkeypatch, path, *extra):
    engine = ClaimStubEngine()
    monkeypatch.setattr("typed_judge.cli.make_engine", lambda name: engine)
    cache = tmp_path / "r.jsonl"
    code = main(["run", "--recipe", V3, "--engine", "fake", "--cache", str(cache),
                 "--out", str(tmp_path / "v.jsonl"), *extra, path])
    verdicts = [json.loads(l) for l in (tmp_path / "v.jsonl").read_text().splitlines()]
    return code, verdicts, engine, cache


def test_sources_lowers_ready_when_the_source_contradicts_the_draft(tmp_path, monkeypatch):
    path = write_pair(tmp_path, "В отчёте: ошибся 3 раза.", "ошибся 30 раз")
    _, verdicts, _, _ = run_v3(tmp_path, monkeypatch, path, "--sources", str(tmp_path / "src"))
    assert [v["verdict"] for v in verdicts] == ["light_edit"]


def test_sources_keeps_ready_when_the_source_agrees(tmp_path, monkeypatch):
    path = write_pair(tmp_path, "В отчёте: ошибся 3 раза.", "ошибся 3 раза")
    _, verdicts, _, _ = run_v3(tmp_path, monkeypatch, path, "--sources", str(tmp_path / "src"))
    assert [v["verdict"] for v in verdicts] == ["ready"]


def test_two_steps_give_one_verdict_per_item_and_two_cache_rows(tmp_path, monkeypatch):
    path = write_pair(tmp_path, "В отчёте: ошибся 3 раза.", "ошибся 30 раз")
    _, verdicts, engine, cache = run_v3(tmp_path, monkeypatch, path, "--sources", str(tmp_path / "src"))
    assert len(verdicts) == 1 and verdicts[0]["item_id"] == "d"
    assert len(cache.read_text().splitlines()) == 2 and engine.calls == 2


def test_run_without_sources_does_not_call_the_engine_twice(tmp_path, monkeypatch):
    path = write_pair(tmp_path, "В отчёте: ошибся 3 раза.", "ошибся 30 раз")
    _, verdicts, engine, cache = run_v3(tmp_path, monkeypatch, path)
    assert engine.calls == 1 and [v["verdict"] for v in verdicts] == ["ready"]
    assert len(cache.read_text().splitlines()) == 1


def test_missing_source_file_leaves_the_verdict_alone(tmp_path, monkeypatch):
    path = write_pair(tmp_path, "В отчёте: ошибся 30 раз.")  # источника для d.md нет
    _, verdicts, engine, _ = run_v3(tmp_path, monkeypatch, path, "--sources", str(tmp_path / "src"))
    assert engine.calls == 1 and [v["verdict"] for v in verdicts] == ["ready"]


def test_sources_on_a_recipe_without_claim_questions_changes_nothing(tmp_path, monkeypatch):
    path = write_pair(tmp_path, "В отчёте: ошибся 30 раз.", "ошибся 30 раз")
    engine = ClaimStubEngine()
    monkeypatch.setattr("typed_judge.cli.make_engine", lambda name: engine)
    code = main(["run", "--recipe", "typed_judge.recipes.draft_lint_v2", "--engine", "fake",
                 "--cache", str(tmp_path / "r.jsonl"), "--sources", str(tmp_path / "src"), path])
    assert code in (0, 1) and engine.calls == 1


def test_cli_has_no_getattr_for_combine_with_claims():
    import pathlib
    import typed_judge.cli as cli_mod
    src = pathlib.Path(cli_mod.__file__).read_text(encoding="utf-8")
    assert "combine_with_claims" not in src


# --- tj run --route: зона сомнения из CLI (бид typed-judge-kit-so7) ---

class DefectStubEngine(ClaimStubEngine):
    """Черновик с ровно одним стилистическим дефектом — ровно на границе ready/light_edit."""

    def __init__(self, defects=(), overclaim=0.1):
        super().__init__()
        self.defects, self.overclaim = set(defects), overclaim

    def ask(self, state, questions):
        from typed_judge.engines import Result
        from typed_judge.questions import Answer, Choice, Noul
        self.calls += 1
        out = {}
        for qid, q in questions.items():
            if isinstance(q, Choice):
                out[qid] = Answer(value=list(q.options)[0], confidence=0.9)
            elif isinstance(q, Noul):
                p = self.overclaim if qid == "overclaim" else (0.9 if qid in self.defects else 0.1)
                out[qid] = Answer(probability=p)
        return Result(answers=out)


def run_route(tmp_path, monkeypatch, engine, *extra):
    monkeypatch.setattr("typed_judge.cli.make_engine", lambda name: engine)
    path = write_pair(tmp_path, "В отчёте: ошибся 3 раза.")
    code = main(["run", "--recipe", V3, "--engine", "fake", "--cache", str(tmp_path / "r.jsonl"),
                 "--out", str(tmp_path / "v.jsonl"), *extra, path])
    return code, [json.loads(l) for l in (tmp_path / "v.jsonl").read_text().splitlines()]


def test_route_sends_a_draft_inside_the_band_to_review_required(tmp_path, monkeypatch):
    code, verdicts = run_route(tmp_path, monkeypatch, DefectStubEngine(defects=["hedging"]), "--route")
    assert verdicts[0]["verdict"] == "review_required" and "defects->1" in verdicts[0]["note"]
    assert code == 1


def test_route_leaves_a_draft_outside_the_band_with_its_own_verdict(tmp_path, monkeypatch):
    code, verdicts = run_route(tmp_path, monkeypatch, DefectStubEngine(), "--route")
    assert verdicts[0]["verdict"] == "ready" and code == 0


def test_without_route_a_borderline_draft_keeps_its_verdict_and_exit_code(tmp_path, monkeypatch):
    code, verdicts = run_route(tmp_path, monkeypatch, DefectStubEngine(defects=["hedging"]))
    assert verdicts[0]["verdict"] == "light_edit" and code == 0


def test_route_on_a_recipe_without_margins_changes_nothing(tmp_path, monkeypatch):
    engine = DefectStubEngine(defects=["hedging"])
    monkeypatch.setattr("typed_judge.cli.make_engine", lambda name: engine)
    path = write_pair(tmp_path, "В отчёте: ошибся 3 раза.")
    code = main(["run", "--recipe", "typed_judge.recipes.draft_lint", "--engine", "fake",
                 "--cache", str(tmp_path / "r.jsonl"), "--out", str(tmp_path / "v.jsonl"),
                 "--route", path])
    verdicts = [json.loads(l) for l in (tmp_path / "v.jsonl").read_text().splitlines()]
    assert code in (0, 1) and verdicts[0]["verdict"] != "review_required"
