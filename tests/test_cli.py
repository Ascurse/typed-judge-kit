import json

from typed_judge.cli import main


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
