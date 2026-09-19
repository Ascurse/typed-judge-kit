import datetime as dt

from typed_judge.blind_duplicates import (
    LabeledItem,
    eligible_for_blind_duplicate,
    rater_pairs_from_doc,
    record_retest,
    schedule_blind_duplicates,
)

TODAY = dt.date(2026, 9, 20)


def test_eligible_excludes_items_labeled_less_than_14_days_ago():
    items = [
        LabeledItem("old", "ready", dt.date(2026, 8, 1)),   # 50 дней назад
        LabeledItem("new", "ready", dt.date(2026, 9, 15)),  # 5 дней назад
    ]
    assert [i.item_id for i in eligible_for_blind_duplicate(items, TODAY)] == ["old"]


def test_schedule_mixes_one_duplicate_per_five_new_items():
    pool = [LabeledItem("old-a", "ready", dt.date(2026, 8, 1)),
            LabeledItem("old-b", "ready", dt.date(2026, 8, 2))]
    new_batch = [f"n{i}" for i in range(12)]
    schedule = schedule_blind_duplicates(new_batch, pool, TODAY)
    assert schedule == [(4, "old-a"), (9, "old-b")]


def test_schedule_skips_ids_not_yet_14_days_old():
    pool = [LabeledItem("too-new", "ready", dt.date(2026, 9, 18))]
    schedule = schedule_blind_duplicates([f"n{i}" for i in range(5)], pool, TODAY)
    assert schedule == []


def test_schedule_empty_when_no_new_batch():
    pool = [LabeledItem("old-a", "ready", dt.date(2026, 8, 1))]
    assert schedule_blind_duplicates([], pool, TODAY) == []


def test_record_retest_appends_pair_without_touching_labels_or_holdout():
    doc = {"labels": {"a": "ready"}, "holdout": ["a"]}
    updated = record_retest(doc, "a", "ready", "light_edit", "2026-08-01", "2026-09-20")
    assert updated["labels"] == {"a": "ready"} and updated["holdout"] == ["a"]
    assert updated["retest_pairs"] == [
        {"id": "a", "first": "ready", "first_date": "2026-08-01",
         "retest": "light_edit", "retest_date": "2026-09-20"}
    ]
    assert doc.get("retest_pairs") is None  # исходный документ не мутирован


def test_rater_pairs_from_doc_empty_when_no_field():
    assert rater_pairs_from_doc({"labels": {}}) == []


def test_rater_pairs_from_doc_extracts_first_retest_tuples():
    doc = {"retest_pairs": [
        {"id": "a", "first": "ready", "retest": "ready"},
        {"id": "b", "first": "ready", "retest": "light_edit"},
    ]}
    assert rater_pairs_from_doc(doc) == [("ready", "ready"), ("ready", "light_edit")]
