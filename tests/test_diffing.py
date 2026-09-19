import pathlib

from typed_judge.diffing import diff_texts, published_report


def test_pure_style_edit_has_no_fact_edits():
    draft = "Мы попробовали новый подход и он хорошо сработал в итоге."
    published = "Мы попробовали новый подход, и он неплохо сработал в итоге."
    r = diff_texts(draft, published)
    assert r.fact_edits == 0
    assert r.style_edits > 0
    assert r.candidate is None


def test_number_substitution_is_a_fact_edit():
    draft = "За 3 месяца R@5 вырос с 13% до 93%."
    published = "За 3 месяца R@5 вырос с 13% до 87%."
    r = diff_texts(draft, published)
    assert r.fact_edits >= 1
    assert r.candidate == "critical"


def test_proper_name_substitution_mid_sentence_is_a_fact_edit():
    draft = "Мы сравнили результат с системой Reranker на том же наборе."
    published = "Мы сравнили результат с системой Colbert на том же наборе."
    r = diff_texts(draft, published)
    assert r.fact_edits >= 1


def test_identical_texts_have_zero_hter():
    r = diff_texts("Один и тот же текст.", "Один и тот же текст.")
    assert r.hter == 0.0
    assert r.style_edits == 0 and r.fact_edits == 0
    assert r.candidate is None


DRAFT_TEXT = "За 3 месяца R@5 вырос с 13% до 93%. Идея сработала хорошо."


def _write_vault(tmp_path: pathlib.Path, edits: str, edits_note: str,
                  published_text: str | None) -> pathlib.Path:
    drafts = tmp_path / "output" / "Content" / "drafts"
    published = tmp_path / "output" / "Content" / "published"
    drafts.mkdir(parents=True)
    published.mkdir(parents=True)
    (drafts / "2026-09-18-tiny-local-judge.md").write_text(
        f"---\ntitle: x\n---\n{DRAFT_TEXT}", encoding="utf-8",
    )
    text_section = f"\n\n## Опубликованный текст\n{published_text}\n" if published_text else ""
    (published / "2026-09-18-tiny-local-judge-thread.md").write_text(
        "---\n"
        "type: published\n"
        f"edits: {edits}\n"
        f'edits_note: "{edits_note}"\n'
        "---\n\n"
        f"Источник: `output/Content/drafts/2026-09-18-tiny-local-judge.md`\n\n"
        f"Краткий пересказ публикации, не сам пост.{text_section}",
        encoding="utf-8",
    )
    # индексная заметка без frontmatter — не пост, не должна попасть в отчёт
    (published / "README.md").write_text("# Published content\nКонвенции полей.", encoding="utf-8")
    return tmp_path


def test_published_report_without_saved_text_falls_back_to_frontmatter_only(tmp_path):
    root = _write_vault(tmp_path, "light", "добавлено «by …»", published_text=None)
    report = published_report(root)
    assert "tiny-local-judge" in report
    assert "нет отдельного текста опубликованной версии" in report
    assert "edits (владелец, frontmatter): light" in report
    assert "добавлено «by …»" in report
    assert "README" not in report


def test_published_report_computes_real_diff_when_text_section_present(tmp_path):
    published_text = "За 3 месяца R@5 вырос с 13% до 87%. Идея сработала хорошо."
    root = _write_vault(tmp_path, "light", "правка числа", published_text=published_text)
    report = published_report(root)
    assert "кандидат" in report.lower()
    assert "HTER-прокси" in report
    labels_path = root / "Inputs" / "labels.json"
    assert not labels_path.exists()


def test_published_report_no_posts_found_says_so(tmp_path):
    (tmp_path / "output" / "Content" / "published").mkdir(parents=True)
    (tmp_path / "output" / "Content" / "drafts").mkdir(parents=True)
    report = published_report(tmp_path)
    assert "published-постов не найдено" in report
