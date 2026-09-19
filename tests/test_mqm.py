from typed_judge.mqm import categories, category_of, plain_verdicts, verdict_of


def test_old_string_form_has_no_category():
    assert verdict_of("ready") == "ready"
    assert category_of("ready") is None


def test_new_dict_form_carries_verdict_and_category():
    entry = {"verdict": "light_edit", "category": "major"}
    assert verdict_of(entry) == "light_edit"
    assert category_of(entry) == "major"


def test_plain_verdicts_reads_mixed_schema_backward_compatibly():
    labels = {
        "a": "ready",
        "b": {"verdict": "heavy_edit", "category": "critical"},
    }
    assert plain_verdicts(labels) == {"a": "ready", "b": "heavy_edit"}


def test_categories_only_lists_entries_that_have_one():
    labels = {
        "a": "ready",
        "b": {"verdict": "light_edit", "category": "minor"},
        "c": {"verdict": "heavy_edit", "category": "critical"},
    }
    assert categories(labels) == {"b": "minor", "c": "critical"}
