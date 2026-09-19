# typed-judge

Typed questions to a model, one batched call, a verdict computed in your code, thresholds calibrated on your own labels.

## What

Write typed questions (Choice / Score / Noul) once, ask them in a single batched call, turn the answers into a verdict with a formula you own, then calibrate `auto` / `flag` / `human` thresholds on your own labeled examples — not on the model's self-reported confidence.

## Install / 60-second demo

```bash
pip install typed-judge
```

No API key needed to try it — the bundled `FakeEngine` returns deterministic, state-dependent answers so you can see the shape of the output immediately:

```bash
printf -- '---\ntitle: t\n---\nЗа 3 месяца R@5 вырос с 13%% до 93%%.\n' > draft.md
tj variants --recipe typed_judge.recipes.draft_lint --engine fake --cache r.jsonl draft.md
```

```
| variant | verdict | score |
|---|---|---|
| factor | heavy_edit | 0.314 |
| holistic | light_edit | 0.9 |
| factor_en | heavy_edit | 0.314 |
```

Verified in a clean venv (`uv build` → fresh `uv venv` → `uv pip install dist/typed_judge-0.1.0-py3-none-any.whl`): `tj --help` exits 0, `tj variants` above prints the same three-row table.

## Numbers we measured

All measured on `draft_lint`, the bundled 10-question recipe, mostly against Gemini Flash-Lite; exact figures below (2026-09-19/20 measurements, this repo's fixtures and `Outputs/2026-09-20-run-*.jsonl`):

- **Batching wins.** One call with all 10 questions is **7.0× faster** than 10 sequential calls for the same document: 1.56 s batched vs 10.92 s sequential-summed (Gemini Flash-Lite, probe doc `2026-09-04-memory-eval-reranker-thread-x`, 1361 chars).
- **The marginal question is cheap.** Once the first question pays for the prompt/schema overhead, each additional question costs ≈ 33 input tokens (781 input tokens for all 10 questions batched vs 486 for one question alone → (781−486)/9 ≈ 33).
- **Jev (TypeSafe System One) is fast and cheap per document.** Median 760 ms per document (1.3–4.3k tokens), $0.0009 for a 10-document batch (see `typed_judge/engines/typesafe.py::cost_usd`, live-checked 2026-09-19: `Outputs/2026-09-19-typesafe-live.md`).
- **Question phrasing changes the verdict.** Asking one holistic "is this ready?" question agreed with owner labels 0/3; the same three drafts scored with the 10-question factor formula agreed 3/3. A single global judgment call is not a substitute for decomposing it.
- **Self-reported confidence doesn't discriminate.** Gemini Flash-Lite's own `confidence` field sits in a narrow 0.88–0.95 band across all 10 drafts regardless of how clear-cut the draft is — don't threshold on it.
- **A one-line fix, zero new model calls.** Comparing the model's own verdict against `hook` as a float (instead of the intended int-like threshold) undercounted agreement; fixing the threshold logic in `combine()` raised agreement between the code's verdict and the model's own holistic verdict from 7/10 to 9/10 — recomputed from the same cached answers, no re-querying.
- **Golden set (10 draft_lint verdicts, cached in `tests/fixtures/draft_lint_results.json`):** code's verdict agrees with the model's own holistic verdict on **9/10**; agrees with the owner's manual labels on **3/4** (5 labels exist, but `2026-09-18-tiny-local-judge` has no cached result, so 4 are usable — 3/4 is a reminder to keep collecting labels, not a target to hit).
- **typesafe vs gemini on the same 10 drafts** (`tj report --compare`, 2026-09-20 live run): **9/10** verdicts agree. The one disagreement — `post-template-lesson-progress-tradeoff` (typesafe: `light_edit`, score 0.555; gemini: `heavy_edit`, score 0.304) — is recorded, not "fixed": different engines, same formula, borderline score, different verdict bucket.

## Engines

- `fake` — deterministic, no network, no keys. Good for demos and CI.
- `typesafe[:model]` — TypeSafe System One / Jev, default model `jev-latest`. Needs `TYPESAFE_API_KEY` (env or `~/.hermes/.env`).
- `gemini[:model]` — Gemini structured output, default model `gemini-3.5-flash-lite`. Needs `GEMINI_API_KEY` or `GOOGLE_API_KEY` (env or `~/.hermes/.env`).

Keys are read via `load_key()` and are never printed or logged — only `mask()` output (`...last4`) may appear in output.

## Calibration

`tj calibrate --recipe <recipe> --cache <cache.jsonl> --labels <labels.json>` reads cached rows (no model calls), applies your recipe's `combine()`, and compares the resulting scores against your labels to fit an `auto_at` threshold (score above which the verdict is trusted without review). Below it is `flag`/`human`.

**v2 (DR-62): the old precision-on-the-same-points fitting was a data leak.** At `n=14`, "precision 1.0" proves nothing — the threshold was picked and scored on the same 14 examples. `calibrate.py` now does two things differently:

- **Frozen holdout.** `labels.json` can carry a top-level `"holdout": [item_id, ...]` list. Those ids are excluded from threshold fitting and only ever show up in an audit line (`split_holdout`); everything else in `"labels"` is calibration data. Old `labels.json` files without a `"holdout"` key still work unchanged — every label goes to calibration, exactly like before.
- **CRC threshold instead of point precision.** `auto_at` is the smallest score threshold whose Conformal Risk Control upper bound `(k+1)/(n+1) ≤ alpha` holds (`alpha=0.05` by default), where `k` is the error count in that auto zone and `n` the full calibration set — not the zone size, which is what makes the bound marginally valid (Angelopoulos et al., [arXiv:2208.02814](https://arxiv.org/abs/2208.02814)). A non-trivial threshold can only exist once `n >= (k+1)/alpha - 1`; otherwise the report prints `auto выключен, coverage 0` and no fitted threshold is offered as a recommendation.

The report itself has three fixed modes, keyed on the calibration `n` (not counting holdout):

| `n` | What gets printed |
|---|---|
| `< 19` | `сертификация невозможна, auto off` — no CRC threshold can exist at this size for any error count, full stop. |
| `19–50` | `ожидаемый риск <= alpha, точечные метрики справочно` — a CRC threshold is shown, but point precision/coverage are reference-only, not statistically certified. |
| `50+` | adds a two-sided Clopper–Pearson confidence interval for the auto zone's precision (stdlib only — no scipy; the beta quantile is found by bisection on the binomial CDF). |

A `cohens_kappa(pairs)` function computes inter-rater agreement for blind test-retest label pairs (protocol: see the labeling task); `report_text` prints a `каппа Коэна` line only when such pairs are actually passed in — there's no pair data yet, so today's reports omit it.

### Claim → method → minimum n

Adapted from the DR-62 research synthesis (Angelopoulos & Bates 2107.07511; Angelopoulos et al. 2208.02814; Miller 2411.00640):

| Claim | Method | Minimum n |
|---|---|---|
| Accuracy ≥ 90% / 95% / 99%, 95% confidence, 0 calibration errors | Clopper–Pearson, one-sided lower bound | 29 / 59 / 299 |
| Accuracy ≥ 90% / 95% / 99%, 95% confidence, 1 calibration error | Clopper–Pearson, one-sided lower bound | 46 / 93 / 473 |
| Two-sided 95% CI on precision, 0 / 1 / 2 errors | Clopper–Pearson, two-sided (`clopper_pearson`) | 72 / 110 / 142 |
| Non-trivial CRC auto threshold, α=0.10, 0 / 1 / 2 errors | Conformal Risk Control (`fit_thresholds`) | 9 / 19 / 29 |
| Non-trivial CRC auto threshold, α=0.05, 0 / 1 / 2 errors | Conformal Risk Control (`fit_thresholds`) | 19 / 39 / 59 |
| Accuracy ≥ 95% without re-inflating α on weekly peeking, 0 / 1 / 2 errors | Anytime-valid betting confidence sequence | 45 / 72 / 98 |
| Labeler self-agreement κ ≥ 0.7 | Blind test-retest, Cohen's κ (`cohens_kappa`) | 25 pairs |

At `n=14` (the owner's original label set, now frozen as holdout — see above), none of these claims are certifiable; that's a correct status, not a regression.

## Where this does not work

Typed judgments are a **gate or classifier**, not a **ranker on top of already-good retrieval**. A Noul-based reranker placed over fusion-retrieval's top-20 made results worse, not better: R@5 dropped from 14/15 to 13/15 (v1) and 12/15 (v2), MRR from 0.744 to 0.63. If retrieval is already decent, don't reach for a typed judgment to reorder it — use it to decide go/no-go or bucket instead.

Thresholds calibrated on a handful of labels don't generalize. 3/4 or 3/5 agreement on a tiny label set is not a result to report as "the calibration works" — see the claim table above for how many labels each kind of statistical statement actually needs.

`draft_lint` judges writing, not facts. On 25 synthetic drafts with a forced critical defect (flipped negation, swapped date/name/number, semantic absurdity) `draft_lint_v2` said `ready` to 20 of them (`tests/fixtures/stress/`, 2026-09-20). The rule "one missed critical defect → `auto` off" is executable: `pytest -m stress` (red today, on purpose).

## Recipes

`typed_judge.recipes.draft_lint` is the bundled recipe: 10 questions (`hook`, `evidence`, `symmetry`, `hedging`, `generic_conclusion`, `tone`, `one_idea`, `top_defect`, `readiness`, `better_as_thread`) plus a `combine()` formula (weighted composite of hook/evidence/tone/one_idea/generic_conclusion, penalized by symmetry/hedging, gated by hook and evidence floors) that maps answers to `ready` / `light_edit` / `heavy_edit`. `VARIANTS`/`COMBINES` also expose a `holistic` (single readiness question) and `factor_en` (English phrasing) variant for the `tj variants` A/B table.

`typed_judge.recipes.screen_incoming` is a guardrail for incoming text (forwards, web pages) before an agent stores or acts on it: 4 questions (`injection`, `relevance`, `noise`, and a 0–3 `hazard` score) mapped to `block` / `skip` / `pass` / `review`. Injection ≥ 0.5 or hazard ≥ 2 blocks outright; noise ≥ 0.6 skips; otherwise relevance decides. On 6 real items (typesafe `jev-latest`, $0.0002 total) it blocked both injection samples and skipped the promo. Its `relevance` question describes one person's research scope — rewrite it for yours.

To calibrate on your own labels: write a `labels.json` with `{"labels": {"<item_id>": "<verdict>"}}` and run `tj calibrate --recipe typed_judge.recipes.draft_lint --cache <your-cache.jsonl> --labels labels.json`. Weights and thresholds live in `combine()` in code, not in the prompt — change the formula, not the model's instructions.

## License

MIT
