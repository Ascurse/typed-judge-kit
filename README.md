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

Verified in a clean venv (`uv build` → fresh `uv venv` → `uv pip install dist/typed_judge-0.2.0-py3-none-any.whl`): `tj --help` exits 0, `tj variants` above prints the same three-row table, and both optional steps below run off the installed wheel (2026-09-21, bead `c5e`).

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

A `cohens_kappa(pairs)` function computes inter-rater agreement for blind test-retest label pairs; `report_text` prints a `каппа Коэна` line only when such pairs are actually passed in, and only calls the agreement "устойчивая согласованность" (reliable) once `n >= 25` pairs — below that it prints a `⚠ n=N < 25` warning instead (`RATER_PAIRS_RELIABLE_MIN`).

**v2 (DR-62 §1.6–1.7, разметка v2): three more pieces, all backward-compatible and all reused via `tj calibrate`/`labels.json` without touching `calibrate.py`'s core logic.**

- **MQM-lite defect categories** (`mqm.py`). A label in `labels.json` can stay a plain string (`"ready"`) or become `{"verdict": "...", "category": "critical" | "major" | "minor"}` (`critical` = a number/fact/legal-risk edit). `mqm.plain_verdicts()` strips categories before handing labels to `calibrate.py`, so old files and `calibrate.py` itself are untouched. The rule "critical → heavy_edit" is deliberately **not** implemented here — that's v3 aggregation.
- **Draft ↔ published diff tool** (`diffing.py`, `tj diff-published --vault-root <path>`). Computes an HTER proxy (`difflib` word-level edit distance / draft length) split into style vs. fact edits by a regex NER filter (digits/dates/percents, or a capitalized word not at a sentence start). Candidate labels are printed for owner confirmation and never written to `labels.json`. It only computes a real diff when the publication note has a `## Опубликованный текст` section with the actual post text — a note that only *describes* the publication (this vault's current two posts) is not diffed against the draft, since that comparison is two unrelated texts, not an edit distance.
- **Blind duplicates** (`blind_duplicates.py`). `schedule_blind_duplicates()` mixes one previously-labeled item (labeled ≥14 days ago) into every ~5 new ones, for undisclosed re-labeling; `record_retest()`/`rater_pairs_from_doc()` store and read the resulting (first, retest) pairs from a new `labels.json` field, `"retest_pairs"` (absent = empty, backward-compatible). `tj calibrate` picks these up automatically and feeds them to `cohens_kappa`.

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

`draft_lint` judges writing, not facts. On 25 synthetic drafts with a forced critical defect (flipped negation, swapped date/name/number, semantic absurdity) `draft_lint_v2` said `ready` to 20 of them and `draft_lint_v3` to 19 (`tests/fixtures/stress/`, 2026-09-20). Facts need a separate step against a source, not better writing questions — see `claim_check` below. The rule "one missed critical defect → `auto` off" is executable: `pytest -m stress` (green for `v3 + claim_check`; `pytest -m stress_v2` keeps the red record for the writing-only recipe).

## Recipes

`typed_judge.recipes.draft_lint` is the bundled recipe: 10 questions (`hook`, `evidence`, `symmetry`, `hedging`, `generic_conclusion`, `tone`, `one_idea`, `top_defect`, `readiness`, `better_as_thread`) plus a `combine()` formula (weighted composite of hook/evidence/tone/one_idea/generic_conclusion, penalized by symmetry/hedging, gated by hook and evidence floors) that maps answers to `ready` / `light_edit` / `heavy_edit`. `VARIANTS`/`COMBINES` also expose a `holistic` (single readiness question) and `factor_en` (English phrasing) variant for the `tj variants` A/B table.

`typed_judge.recipes.screen_incoming` is a guardrail for incoming text (forwards, web pages) before an agent stores or acts on it: 4 questions (`injection`, `relevance`, `noise`, and a 0–3 `hazard` score) mapped to `block` / `skip` / `pass` / `review`. Injection ≥ 0.5 or hazard ≥ 2 blocks outright; noise ≥ 0.6 skips; otherwise relevance decides. On 6 real items (typesafe `jev-latest`, $0.0002 total) it blocked both injection samples and skipped the promo. Its `relevance` question describes one person's research scope — rewrite it for yours.

`typed_judge.recipes.draft_lint_v3` is the recipe the rest of this section is about, and the one `pytest -m stress` certifies. It replaces the Score/positive-Noul questions with binary defect questions (each with an explicit "example of a violation"), and aggregates them with unit weights (count of style defects: 0 → `ready`, 1–2 → `light_edit`, ≥3 → `heavy_edit`) plus one critical question, `overclaim`, that downgrades `ready` to `light_edit` at ≥ 0.76. **It is worse than v2 on the owner's labels and better on the thing that matters.** On the same 14 labels it agrees 6/14 (`rep1`; 8/14 on `rep2`/`rep3`, flip rate 0.14) against v2's 11/14, permutation p = 0.883 — chance level. Cause, from the cached run: the binary style questions fire almost never (across 14 drafts × 8 questions, no draft reaches the `heavy_edit` count of 3), so the additive part is dead and `overclaim` alone decides all 14 verdicts. But those 14 labels are a frozen holdout that certifies nothing at that size, and on the gate that is executable — one missed critical defect turns `auto` off — v2 fails 20/25 and v3 + `claim_check` passes 25/25. So v3 is the default here and v2 stays in the tree as the recorded measurement it came from; `pytest -m stress_v2` keeps v2's red record runnable. v1 (`draft_lint`) remains as the demo recipe and the `tj variants` A/B example.

Two earlier shapes of this recipe are recorded in the beads tracker rather than the code: `unsourced` as a single question that the model read as "a claim exists" (separation −1.00, split into `has_claim`/`has_source` in bead `08p`), and `overclaim` as a veto that set `heavy_edit` outright (bead `ov0`). The veto version used the threshold 0.76 that had been calibrated in v2 for a *different* consequence — downgrading `ready` to `light_edit` — so all 8 firings were guaranteed misses against a label set containing no `heavy_edit` at all. Restoring the calibrated consequence is what moved agreement from 3/14 to 6/14. `scripts/overclaim_veto_check.py` re-runs the fixture-level check from the cached h37 answers and exits non-zero if any firing ever produces `heavy_edit` again.

Bead `k55` then gave `overclaim` the positive class it never had: five minimal `base`/`overclaim` pairs, the same text plus one appended conclusion stronger than the data in it supports. On that axis the question separates cleanly — 5/5 firing at p 0.91–0.97 against 0/5 on the unappended texts (max 0.56), separation 1.000 at the inherited 0.76, which sits inside the empty 0.56–0.91 gap rather than being fitted to it. With n=5 per class the Clopper-Pearson intervals ([0.478, 1.000] vs [0.000, 0.522]) barely fail to overlap, so this supports leaving the threshold alone rather than proving it. The consequence stays `light_edit`: fixtures say whether a text overclaims, not what verdict an editor gives it, and none of the 14 labels is `heavy_edit`.

Bead `0py` did the same for the two style questions the 13k calibration could not decide, `topic_sprawl` and `loose_end` (0/10 and 0.1/0.0 on the ru pairs, because no ru text contains either defect). Ten more synthetic minimal pairs: the same `base` text plus two sentences drifting into two unrelated topics, or one sentence naming a result, remainder or promised follow-up that is never delivered. `topic_sprawl` separates cleanly: 5/5 firing at p 0.80–0.90 against 0/5 on the bases (max 0.07), and no other fixture kind exceeds 0.12 — kept as is at 0.5. `loose_end` separates less: 5/5 at p 0.80–0.94, but one base fires (`base-02-weekly-review`, p 0.51), so separation is 0.800 at 0.5. Across all 35 fixtures that carry no loose end, 3 cross 0.5 (0.51, 0.57, 0.60; 3/35, CI [0.018, 0.231]) and each one flips `ready` to `light_edit`; the empty gap is 0.60–0.80, so 0.5 sits below it. Decision: keep the wording and the pre-registered 0.5 — moving it on 5 synthetic positives is the fitting the rule below forbids. The positives are loud by construction, so 5/5 measures "can the question see an obvious tail", not its false-fire rate on natural text; that number is open (bead `490`).

Bead `p6g` closed the last of the three transfer errors in v3: the threshold 0.76 was calibrated on v2's wording of `overclaim` and inherited by a v3 wording that appends an explicit "example of a violation". Running both wordings over the same 70 fixtures, with everything else in the batch identical (`scripts/overclaim_wording_compare.py`, $0.0058), the shift is real and one-directional — mean Δp −0.115, max |Δ| 0.30, 8 of 70 fixtures cross 0.76, firing rate over the whole set 0.214 → 0.100. It eats false fires, not signal: on the `base`/`overclaim` minimal pairs both wordings separate 1.000 at 0.76, and mean p on the bases falls 0.514 → 0.374 while the positives hold at 0.950 → 0.944. Threshold kept. It also does not explain the old 9/14-drafts vs 3/50-fixtures gap: wording is worth ~2× of a ~10× gap, the rest is the corpus.

`typed_judge.claim_check` (bead `q36`) is the fact-checking step the writing recipes cannot be: draft and source in one state, and a judgment on whether any concrete claim contradicts the source or is absent from it. On the h37 critical fixtures, with each fixture's paired `base` text as the source, one holistic question catches 25/25 with 0/5 false fires on the bases — `draft_lint_v3` alone misses 19 of those 25, so this is what turns `pytest -m stress` green. **The two-step decomposition from the literature lost to the single question here**: splitting the draft into claim-bearing sentences (deterministic — the engine returns no text, so extraction cannot be a model call) and asking per claim catches 19/25 in the defect wording and 18/25 in the positive wording. The gap is `negation_flip` (1/5 per claim, 5/5 holistic): a flipped "not" leaves every number, name and date intact, so a per-claim question anchored on matching those sees nothing wrong. Both wordings were asked in the same run because bead `08p` had already shown one plausible phrasing can invert; here they agree, which is itself the check. Limits, unchanged from the literature: multi-step and arithmetic relations between claims are not covered. And the source here is synthetic and near-verbatim — a real working note is shorter, differently worded and full of unrelated material, so this number does not transfer to production (bead for the real run below).

`typed_judge.routing` (bead `qei`) is the FrugalGPT-style cascade step: the code, not the model, decides what it will not decide alone. Two independent triggers send an item to `review_required` — proximity to a decision boundary (pre-registered band of 0.10 of each axis' range, ±0.05 around it) and disagreement across repeated calls. The first measurement rewrote the feature: a band on the composite score alone caught **0 of 14** drafts, because all 14 composites sit in one clump (0.82–0.93, plus one 0.639) and what actually splits `ready` from `light_edit` there is not the 0.72 threshold but the recipe's gates, `hook >= 2` and `evidence >= 0.6`. So `route()` takes margins on *every* axis the verdict depends on, each normalized by its own scale. With all four axes: 1/14 in the band, 2/14 from repeat disagreement, no overlap between them, 3/14 (0.214) to review, 0.786 straight through. Precision is not claimable at this n — of the judge's 3 disagreements with the owner's labels the router catches 1, where picking 3 of 14 at random would catch 0.64 on average. Width stays pre-registered and untuned until there are 30+ labels (bead `6rx`).

Bead `sqd` then ran `claim_check` on **real** pairs, which the synthetic run could not: 10 of the 14 drafts carry a `Source material` section — the owner's own working notes the post was written from, 87–249 words, shorter than the draft, differently worded and covering only part of it (`scripts/claim_check_drafts.py`, $0.0014). These posts were published, so there is no planted error to catch; what this measures is the false-fire rate that decides whether the step is usable as a veto at all. The holistic question fires on **1 of 10** (0.100) — usable, given its only consequence is downgrading `ready` to `light_edit`. The per-claim path flags **20 of 70** claims (0.286), which is too noisy to gate on, and that is the same verdict the synthetic run reached from the other side. Caveat: `extract_claims` caps at 8 claims and 8 of the 10 drafts hit that cap, so the per-claim number is a rate over truncated drafts, and one draft yields no claims at all under the current surface-feature rule.

### Running the two optional steps

Both extra steps are off by default: `tj run` without flags produces the same verdicts, the same cache
keys and the same number of engine calls it did before they existed.

```bash
# claim-vs-evidence: the source for <item_id>.md is read from sources/<item_id>.md
tj run --recipe typed_judge.recipes.draft_lint_v3 --engine typesafe --cache r.jsonl \
       --sources sources/ drafts/*.md
```

A recipe opts in by declaring `CLAIM_QUESTIONS`; the second call goes into the same cache as separate
rows and `verdict.apply` groups them back by `item_id`, so a draft still gets exactly one verdict. A
draft with no matching source file is left alone — silence from the source is not a reason to
downgrade.

```bash
# borderline items to review_required instead of a verdict (exit 1)
tj run --recipe typed_judge.recipes.draft_lint_v3 --engine typesafe --cache r.jsonl --route drafts/*.md
```

A recipe opts in by declaring `margins(a, score)` — the distances to its own boundaries, each
normalized by its own scale, because only the recipe knows them. For `draft_lint_v3` those are the
style-defect count against its two gates (scale 0..8) and `overclaim` against 0.76 (scale 0..1).
**On this recipe the flag is a measurement tool, not a CI gate yet:** on the 14 real drafts it routes
**9 of 14** (0.643, `rep1.jsonl` of the 2026-09-20 run, recomputed from cache with no new calls),
against 3/14 for the v2 axes in bead `qei`. Almost all of it is the `overclaim` axis — those
probabilities sit in one clump at 0.59–0.87 and 8 of 14 fall inside ±0.05 of 0.76, so the band is
measuring how dense the distribution is there, not how borderline a draft is. The defect-count axis
fired once and is degenerate by construction: the count is an integer, so a ±0.4-defect band is an
exact hit on 1 or 3 rather than a neighbourhood. Width and axes stay untouched until there are 30+
labels (bead `6rx`).

**Rule: weights and thresholds live in code, and fitting them on small n is forbidden.** With n=14 any weight tuned to the labels is fitted to noise (Dawes 1979 — unit weights generalize better than weights fitted on small samples). Thresholds are pre-registered in a note before the run that measures them, and are not adjusted afterwards to improve agreement; an unwanted number is a result, not a reason to re-tune. The 14 labels are a frozen holdout (see Calibration), so any agreement computed on them is a direction check, never proof.

To calibrate on your own labels: write a `labels.json` with `{"labels": {"<item_id>": "<verdict>"}}` (or `{"<item_id>": {"verdict": "...", "category": "critical|major|minor"}}` for MQM-lite, see above) and run `tj calibrate --recipe typed_judge.recipes.draft_lint --cache <your-cache.jsonl> --labels labels.json`. Weights and thresholds live in `combine()` in code, not in the prompt — change the formula, not the model's instructions.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) — released versions, and the measurements that decided each feature.

## License

MIT
