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


def test_calibrate_prints_agreement_and_warning(tmp_path, capsys):
    paths = write_drafts(tmp_path)
    cache = tmp_path / "r.jsonl"
    main(["run", "--recipe", "typed_judge.recipes.draft_lint", "--engine", "fake", "--cache", str(cache), *paths])
    (tmp_path / "labels.json").write_text(json.dumps({"labels": {"draft-0": "ready", "draft-1": "light_edit"}}))
    code = main(["calibrate", "--recipe", "typed_judge.recipes.draft_lint", "--cache", str(cache),
                 "--labels", str(tmp_path / "labels.json"), "--out", str(tmp_path / "t.json")])
    out = capsys.readouterr().out
    assert code == 0 and "согласие вердикта с метками" in out and "/2" in out and "ненадёжны" in out
    assert json.loads((tmp_path / "t.json").read_text())["n"] == 2


def test_variants_table(tmp_path, capsys):
    (path,) = write_drafts(tmp_path, 1)
    code = main(["variants", "--recipe", "typed_judge.recipes.draft_lint", "--engine", "fake",
                 "--cache", str(tmp_path / "r.jsonl"), path])
    out = capsys.readouterr().out
    assert code == 0 and "| factor |" in out and "| holistic |" in out and "| factor_en |" in out


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
