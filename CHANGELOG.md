# Changelog

Numbers in this file are measured, not estimated; each one names the bead, script or fixture set it
comes from. Where a measurement failed to support a feature, the failure is listed too — negative
results are the point of this repo, not an embarrassment to hide in the tracker.

## 0.2.0 — unreleased

`pyproject.toml` is at 0.2.0; the wheel is not built yet (bead `c5e`). `dist/` still carries 0.1.0.

### Recipes

- **`draft_lint_v2`** — `overclaim >= 0.76` downgrades `ready` to `light_edit`. The threshold was
  pre-registered before the run that measured it and has not been moved since (bead `k55`:
  separation 1.000 on 5 minimal `base`/`overclaim` pairs, firing p 0.91–0.97 against max 0.56 on the
  unappended texts; the 0.56–0.91 gap is empty).
- **`draft_lint_v3`** — binary defect questions with an explicit "example of a violation" instead of
  Score/positive-Noul, unit weights over 8 style defects, `overclaim` isolated as a critical class
  (beads `zin`, `wnh`, `ov0`, `08p`, `p6g`). On the owner's 14 labels it agrees 6/14 against v2's
  11/14 (permutation p = 0.883 — chance level); it is the default recipe anyway, because the label
  set is a frozen holdout of 14 and the stress gate is what the recipe is actually for.
- **`screen_incoming`** — guardrail for incoming text before an agent stores or acts on it: 4
  questions mapped to `block` / `skip` / `pass` / `review`. On 6 real items (typesafe `jev-latest`,
  $0.0002) it blocked both injection samples and skipped the promo.
- **`claim_check`** (beads `q36`, `sqd`, `6qa`) — the fact-checking step the writing recipes cannot
  be: draft and source in one state. On the h37 critical fixtures the holistic question catches
  **25/25** with 0/5 false fires on the bases, which is what turns `pytest -m stress` green
  (`draft_lint_v3` alone misses 19 of those 25). On 10 **real** draft/`Source material` pairs with no
  planted errors it false-fires on **1 of 10** (0.100).
  - The two-step decomposition from the literature **lost** to the single question and is not in any
    verdict path: 19/25 and 18/25 on the synthetic set, 20/70 (0.286) false fires on the real pairs.
    `extract_claims`/`questions_for`/`unsupported` stay in the tree as the research path that
    reproduces both measurements.

### CLI

- **`tj run --sources DIR`** (bead `x5r`) — takes each draft's source from `DIR/<item_id>.md` and
  runs the `claim_check` step as a second call, into the same cache. Without the flag, or on a recipe
  without `CLAIM_QUESTIONS`, nothing changes: same verdicts, same cache keys, same engine call count.
  A missing source file is not a downgrade — silence from the source does not veto.
- **`tj run --route`** (bead `so7`) — borderline items go to `review_required` instead of a verdict,
  by proximity to the recipe's own boundaries (`margins()`) and by disagreement across repeats. Off
  by default. On the 14 real drafts it routes **9 of 14** (0.643), driven almost entirely by the
  `overclaim` axis, whose probabilities cluster at 0.59–0.87 with 8 of 14 inside ±0.05 of the 0.76
  threshold — at this band width the flag measures the density of the distribution, not
  borderline-ness. Usable for measurement, not for CI, until the width is calibrated on 30+ labels
  (bead `6rx`).
- **`review_required` now exits 1**, alongside `human` — a borderline item handed to a person must
  not pass a CI gate silently.
- **One verdict per `item_id`** (bead `x5r`). `verdict.apply` groups cache rows by item: the first
  row carries the recipe's answers, the rest arrive as `combine`'s optional second argument. A recipe
  with the old `combine(a)` signature never sees a second argument.
- **`tj diff-published --vault-root <path>`** — draft ↔ published HTER proxy, split into style and
  fact edits by a regex NER filter. Candidate labels are printed for confirmation, never written.

### Calibration

- **CRC threshold replaces point precision** (bead `7mb`, DR-62). `auto_at` is the smallest threshold
  whose Conformal Risk Control bound `(k+1)/(n+1) <= alpha` holds. Fitting a threshold and scoring it
  on the same 14 points was a data leak; at `n < 19` the report now prints
  `сертификация невозможна, auto off` and offers no threshold at all.
- **Frozen holdout** — `labels.json` can carry a top-level `"holdout"` list, excluded from fitting.
  Files without the key behave exactly as before.
- **Three report modes** keyed on calibration `n` (`< 19`, `19–50`, `50+`), with a two-sided
  Clopper–Pearson interval at 50+ (stdlib only, bisection on the binomial CDF).
- **Cohen's κ for blind test-retest pairs** — printed only when pairs are passed, and called reliable
  only at 25+ pairs.
- **MQM-lite categories** (`mqm.py`) — a label may stay a plain string or become
  `{"verdict", "category"}`; categories are stripped before calibration, so old files still work.
- **Blind duplicates** (`blind_duplicates.py`) — schedules undisclosed re-labeling of one older item
  per ~5 new ones and stores the pairs in `"retest_pairs"`.

### Measurements that changed the code

- **`unsourced` was one question measuring the wrong thing** (bead `08p`): the model read "a claim
  with no source" as "a claim exists" — separation −1.00, vetoing 5 of 5 clean base fixtures. Split
  into `has_claim`/`has_source` with the conjunction in code (separation 0.65) and removed from the
  verdict entirely; there is no calibrated threshold for it.
- **`overclaim` as a hard veto was wrong** (bead `ov0`): it set `heavy_edit` using a threshold
  calibrated for downgrading `ready` to `light_edit`, so all 8 firings were guaranteed misses against
  a label set with no `heavy_edit` in it. Restoring the calibrated consequence moved agreement from
  3/14 to 6/14. `scripts/overclaim_veto_check.py` fails if any firing produces `heavy_edit` again.
- **Wording shifts probabilities, and the threshold survived it anyway** (bead `p6g`): adding
  "example of a violation" moves `overclaim` by mean Δp −0.115 over 70 fixtures, 8 of them crossing
  0.76, firing rate 0.214 → 0.100. It eats false fires, not signal — both wordings separate 1.000 on
  the minimal pairs. Threshold kept.
- **Batch contamination looked for and not found** (bead `3jk`) — isolated vs batched calls,
  binarized answers, Hamming distance: no priming detected, so the single batched call stays.
- **EN vs RU** — no verdict difference between languages; RU is less reproducible across repeats.
- **`loose_end` is not settled** (bead `0py`): 5/5 on synthetic tails at p 0.80–0.94, but 3 of 35
  fixtures without a loose end cross the 0.5 threshold (0.51, 0.57, 0.60), and the empty gap is
  0.60–0.80 — the threshold sits below it. Left at the pre-registered 0.5; the real false-fire rate
  is open (bead `490`).
- **A typed judgment is a gate, not a ranker** — a Noul reranker over fusion-retrieval's top-20 made
  results worse: R@5 14/15 → 13/15 (v1) and 12/15 (v2), MRR 0.744 → 0.63.

## 0.1.1 — 2026-09-20

- Corrupted cache lines are skipped with a warning instead of killing the run, and an unterminated
  tail gets its newline back before appending.
- Cost is reported in the markdown table; `cost_usd` added to the Gemini adapter.
- PyPI publishing via trusted publishing on `v*` tags.

## 0.1.0 — 2026-09-19

First release: typed questions (`Choice` / `Score` / `Noul`), one batched engine call per item with a
jsonl cache keyed on (engine, state, questions), a verdict computed by the caller's `combine()` with
`human` as the only fallback, threshold fitting against the caller's own labels, the `draft_lint`
recipe, `tj` (`run` / `calibrate` / `variants` / `report`), markdown reports, and TypeSafe (Jev),
Gemini and deterministic fake engines.

Measured at this point: one batched call is **7.0×** faster than 10 sequential ones (1.56 s vs
10.92 s summed, Gemini Flash-Lite, 1361-char probe doc); each question past the first costs ≈ 33
input tokens; Jev runs at a median 760 ms per document, $0.0009 for a 10-document batch.

Robustness decided in this release and unchanged since: engine errors are never cached, so a
transient failure cannot become permanent; `tj` exits 2 on bad arguments, a bad recipe or a missing
file and 1 on an engine failure; markdown cells escape `|` and newlines, so an error message cannot
break the report table; the `gemini` and `typesafe` adapters reject empty candidates/parts and a null
`choice` value rather than parsing them into a verdict.
