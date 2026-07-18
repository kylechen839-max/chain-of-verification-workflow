# CoVe Evaluation Summary

Latest local benchmark:

```bash
python3 run_cove_evaluation.py \
  --model deepseek-coder:1.3b \
  --max-questions 2 \
  --num-predict 512 \
  --output results/evaluations/cove_evaluation_results.deepseek-coder.local.json
```

## Environment

- Runtime: local Mac through Ollama
- Model: `deepseek-coder:1.3b`
- Benchmark prompts: 6
- Modes compared: direct, joint CoVe, factored CoVe

## Aggregate Results

| Mode | Total Time | Avg Time | Total Verification Questions | Prompts With Checks | Avg Answer Length |
|---|---:|---:|---:|---:|---:|
| Direct | 21.20s | 3.53s | 0 | 0/6 | 1761 chars |
| Joint CoVe | 19.79s | 3.30s | 1 | 1/6 | 1656 chars |
| Factored CoVe | 67.83s | 11.30s | 8 | 4/6 | 1142 chars |

## Observations

- Factored CoVe is slower, but it now performs real verification on most prompts after improving question parsing for messy local-model output.
- Joint CoVe is unreliable with `deepseek-coder:1.3b`; it often ignores the strict JSON contract or returns placeholder-like content.
- The small DeepSeek model is useful for workflow testing, but not reliable enough for factual-quality conclusions without manual scoring.
- Local Mac runs are faster than the current CPU-only Google Compute VM for these small Ollama models.

## Confined Database Tests

The evaluator now supports writing each run into a confined result database. A
local SQLite database was used for isolation:

```bash
--database-url sqlite:///cove_results.confined.local.db
```

The local database is ignored by Git. It currently contains 7 runs and 57 result
rows:

| Run | Model | Settings | Mode Rows | Total Time | Verification Questions |
|---:|---|---|---:|---:|---:|
| 1 | `deepseek-coder:1.3b` | 1 prompt, max_questions=2, num_predict=512 | 3 | 11.22s | 3 |
| 2 | `deepseek-r1:1.5b` | 2 prompts, max_questions=3, num_predict=768 | 6 | 95.83s | 3 |
| 3 | `deepseek-coder:6.7b` | 1 prompt, max_questions=3, num_predict=768 | 3 | 68.98s | 6 |
| 4 | `deepseek-coder:6.7b` | 2 prompts, max_questions=4, num_predict=1024 | 6 | 148.70s | 15 |
| 5 | `deepseek-coder:6.7b` | 3 prompts, max_questions=5, num_predict=1280 | 9 | 277.93s | 28 |
| 6 | `deepseek-coder:6.7b` | 4 prompts, max_questions=6, num_predict=1536 | 12 | 489.57s | 37 |
| 7 | `deepseek-coder:6.7b` | 6 prompts, max_questions=6, num_predict=1536 | 18 | 766.20s | 58 |

## Upscale Notes

- `deepseek-coder:6.7b` was pulled successfully through Ollama.
- The 6.7B model produced more parseable verification questions than
  `deepseek-r1:1.5b` in these tests.
- The upscaled 6.7B run is much slower than the 1.3B baseline, so use small
  prompt limits while iterating.
- Supabase is wired through the same runner. The direct database host is
  IPv6-only from this Mac, so the Supabase pooler URI is the working path.

## Supabase Results

The project `AI_Hallucination_Proj` is active and healthy in Supabase. The
pooler connection now works with the permanent database password.

Remote `cove_test` now contains:

| Run | Write Path | Model | Rows | Total Time | Verification Questions |
|---:|---|---|---:|---:|---:|
| 1 | Management API sync | `deepseek-coder:6.7b` | 18 | 766.20s | 58 |
| 2 | Direct temporary Postgres role | `supabase-direct-temp-smoke` | 1 | 0.00s | 0 |
| 3 | Direct temporary Postgres role | `deepseek-coder:6.7b` | 3 | 64.32s | 6 |
| 4 | Direct permanent Postgres pooler | `deepseek-coder:6.7b` | 6 | 149.93s | 12 |
| 5 | Direct permanent Postgres pooler | `deepseek-coder:6.7b` | 12 | 342.33s | 31 |
| 6 | Direct permanent Postgres pooler | `deepseek-coder:6.7b` | 18 | 589.23s | 48 |

Run 6 is the full six-prompt dataset at `max_questions=4` and
`num_predict=1024`. It completed under the 10-minute Google Compute escalation
threshold, so the full benchmark stayed local.

## NASA Article Runs

The NASA source corpus comes from
`Rohan-Gambhir/Hallucinations`. Its loader creates `public.nasa_articles` from
NASA NTRS records on black holes and gravitational waves. The live table has
500 rows with article metadata and abstracts; there is not a separate full-text
chunk/vector table in this Supabase project.

The NASA prompt file `benchmarks/cove_benchmark_questions_nasa_30.json` was
generated from `public.nasa_articles`. Each prompt includes only article
metadata/abstract facts and instructs the model not to add outside facts.

For these runs, `joint_cove` was skipped. Results compare only:

- `direct`: baseline answer for the article prompt
- `factored_cove`: draft, self-contained verification questions, blind
  verification answers, and final rewrite

The verification-answer step receives only the verification question. It does
not receive the direct baseline response or draft answer.

| Run | Runtime | Prompt Count | Rows | Total Time | Verification Questions |
|---:|---|---:|---:|---:|---:|
| 8 | Local Mac | 1 | 2 | 34.62s | 3 |
| 9 | Local Mac | 12 | 24 | 375.68s | 36 |
| 10 | Local Mac | 24 | 48 | 798.27s | 72 |

Runs 8-10 are preserved as no-context baselines. They exposed a bug in the NASA
verification step: verification answers were blind to the Supabase article
record, so the model sometimes responded that it lacked database or internet
access instead of answering from the NASA article.

That bug is fixed in the context-backed NASA runs. For article prompts,
`factored_cove` now retrieves the matching row from `public.nasa_articles` and
passes it to the verification-answer step with this instruction:

```text
Use the following pieces of context to answer the question. If you don't know the answer, just say that you don't know; don't try to make up an answer.
```

The verifier still does not receive the draft answer or direct baseline answer.
It receives only the verification question plus the retrieved NASA article
context. The raw result payload stores `verification_contexts` for audit.

| Run | Runtime | Prompt Count | Rows | Total Time | Verification Questions | Notes |
|---:|---|---:|---:|---:|---:|---|
| 11 | Local Mac | 1 | 2 | 35.23s | 3 | Context smoke test |
| 16 | Local Mac | 24 | 48 | 712.12s | 72 | Corrected context-backed run |
| 17 | Local Mac | 100 | 200 | 3308.67s | 300 | Corrected context-backed upscale run |

Run 16 was scanned for the earlier failure modes across all 72 verification
answers: 0 database-access refusals, 0 draft-dependent verification questions,
and 0 flagged speculative answers.

## NASA Hallucination Summary

Manual hallucination scores for run 16 are stored in
`results/scoring/cove_evaluation_results.nasa.deepseek-coder-6.7b.local.24.context.hallucination_scores.json`.
The scoring scale is:

- `0`: none obvious
- `1`: minor/uncertain
- `2`: major invented claims

For the main comparison, "without CoVe" means the `direct` answer and
"factored CoVe" means the final rewritten answer after the draft, verification
questions, context-backed verification answers, and final rewrite.

| Mode | Outputs | Score 0 | Score 1 | Score 2 | Any Hallucination Rate | Major Hallucination Rate | Avg Score |
|---|---:|---:|---:|---:|---:|---:|---:|
| Without CoVe (`direct`) | 24 | 9 | 12 | 3 | 62.5% | 12.5% | 0.7500 |
| Factored CoVe final | 24 | 14 | 7 | 3 | 41.7% | 12.5% | 0.5417 |

On this NASA metadata benchmark, factored CoVe reduced the share of outputs
with any hallucination from 62.5% to 41.7%, a 20.8 percentage-point absolute
reduction. The rate of major hallucinations did not change: both modes had 3
major hallucinations out of 24 outputs.

The initial CoVe baseline draft was also scored for comparison. It had 5
score-0 outputs, 18 score-1 outputs, and 1 score-2 output, for a 79.2% any
hallucination rate, a 4.2% major hallucination rate, and an average score of
0.8333. This suggests the verification-and-rewrite step reduced many minor
metadata distortions from the initial draft, though it did not eliminate major
errors in the final answer.

The 100-prompt upscale benchmark is stored in:

- Questions: `benchmarks/cove_benchmark_questions_nasa_100.json`
- Results: `results/evaluations/cove_evaluation_results.nasa.deepseek-coder-6.7b.local.100.context.json`
- Scores: `results/scoring/cove_evaluation_results.nasa.deepseek-coder-6.7b.local.100.context.hallucination_scores.json`

The 100-prompt scores were generated with deterministic NASA metadata checks
in `score_nasa_hallucinations.py`. The scorer flags concrete contradictions
such as wrong NTRS URLs, DOI/report-number conflicts, wrong document type
claims, and unsupported metadata-role claims like treating Legacy CDMS as an
author affiliation, publication venue, or research location. Omissions are not
penalized.

| Mode | Outputs | Score 0 | Score 1 | Score 2 | Any Hallucination Rate | Major Hallucination Rate | Avg Score |
|---|---:|---:|---:|---:|---:|---:|---:|
| Without CoVe (`direct`) | 100 | 43 | 46 | 11 | 57.0% | 11.0% | 0.6800 |
| Factored CoVe final | 100 | 60 | 26 | 14 | 40.0% | 14.0% | 0.5400 |

On the 100-prompt upscale, factored CoVe reduced the share of outputs with any
detected hallucination from 57.0% to 40.0%, a 17.0 percentage-point absolute
reduction. Major hallucinations increased slightly under this deterministic
scoring pass, from 11.0% to 14.0%. The average hallucination score still
improved from 0.6800 without CoVe to 0.5400 with factored CoVe.

## NASA Multi-Trial Upscale

The requested 100-, 200-, and 300-question benchmark matrix is complete. Each
size has three trials, comparing the baseline `direct` answer against the final
`factored_cove` answer. All runs used local Ollama `deepseek-coder:6.7b`,
`max_questions=3`, `num_predict=768`, skipped `joint_cove`, and used
context-backed NASA verification answers.

Aggregate scores are stored in
`results/scoring/nasa_multi_trial_hallucination_summary.json`.

| Prompt Count | Trials | Outputs Per Mode | Mode | Score 0 | Score 1 | Score 2 | Any Hallucination Rate | Major Hallucination Rate | Avg Score |
|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|
| 100 | 3 | 300 | Without CoVe (`direct`) | 129 | 138 | 33 | 57.0% | 11.0% | 0.6800 |
| 100 | 3 | 300 | Factored CoVe final | 180 | 78 | 42 | 40.0% | 14.0% | 0.5400 |
| 200 | 3 | 600 | Without CoVe (`direct`) | 330 | 207 | 63 | 45.0% | 10.5% | 0.5550 |
| 200 | 3 | 600 | Factored CoVe final | 420 | 108 | 72 | 30.0% | 12.0% | 0.4200 |
| 300 | 3 | 900 | Without CoVe (`direct`) | 558 | 240 | 102 | 38.0% | 11.3% | 0.4933 |
| 300 | 3 | 900 | Factored CoVe final | 684 | 132 | 84 | 24.0% | 9.3% | 0.3333 |

Across all nine trials, there were 1,800 outputs per mode. Factored CoVe
reduced the any-hallucination rate from 43.5% to 28.7%, a 14.8 percentage-point
absolute reduction. The major hallucination rate was unchanged overall at
11.0%, while the average hallucination score improved from 0.5450 to 0.3967.

Per-trial runtimes:

| Prompt Count | Trial | Total Runtime | Verification Questions |
|---:|---:|---:|---:|
| 100 | 1 | 3308.67s | 300 |
| 100 | 2 | 3307.05s | 300 |
| 100 | 3 | 3298.68s | 300 |
| 200 | 1 | 6874.60s | 600 |
| 200 | 2 | 6860.52s | 600 |
| 200 | 3 | 6871.67s | 600 |
| 300 | 1 | 10154.06s | 900 |
| 300 | 2 | 10244.21s | 900 |
| 300 | 3 | 10148.09s | 900 |

The trial artifacts are:

| Prompt Count | Trial | Result File | Score File |
|---:|---:|---|---|
| 100 | 1 | `results/evaluations/cove_evaluation_results.nasa.deepseek-coder-6.7b.local.100.context.json` | `results/scoring/cove_evaluation_results.nasa.deepseek-coder-6.7b.local.100.context.hallucination_scores.json` |
| 100 | 2 | `results/evaluations/cove_evaluation_results.nasa.deepseek-coder-6.7b.local.100.trial2.context.json` | `results/scoring/cove_evaluation_results.nasa.deepseek-coder-6.7b.local.100.trial2.context.hallucination_scores.json` |
| 100 | 3 | `results/evaluations/cove_evaluation_results.nasa.deepseek-coder-6.7b.local.100.trial3.context.json` | `results/scoring/cove_evaluation_results.nasa.deepseek-coder-6.7b.local.100.trial3.context.hallucination_scores.json` |
| 200 | 1 | `results/evaluations/cove_evaluation_results.nasa.deepseek-coder-6.7b.local.200.trial1.context.json` | `results/scoring/cove_evaluation_results.nasa.deepseek-coder-6.7b.local.200.trial1.context.hallucination_scores.json` |
| 200 | 2 | `results/evaluations/cove_evaluation_results.nasa.deepseek-coder-6.7b.local.200.trial2.context.json` | `results/scoring/cove_evaluation_results.nasa.deepseek-coder-6.7b.local.200.trial2.context.hallucination_scores.json` |
| 200 | 3 | `results/evaluations/cove_evaluation_results.nasa.deepseek-coder-6.7b.local.200.trial3.context.json` | `results/scoring/cove_evaluation_results.nasa.deepseek-coder-6.7b.local.200.trial3.context.hallucination_scores.json` |
| 300 | 1 | `results/evaluations/cove_evaluation_results.nasa.deepseek-coder-6.7b.local.300.trial1.context.json` | `results/scoring/cove_evaluation_results.nasa.deepseek-coder-6.7b.local.300.trial1.context.hallucination_scores.json` |
| 300 | 2 | `results/evaluations/cove_evaluation_results.nasa.deepseek-coder-6.7b.local.300.trial2.context.json` | `results/scoring/cove_evaluation_results.nasa.deepseek-coder-6.7b.local.300.trial2.context.hallucination_scores.json` |
| 300 | 3 | `results/evaluations/cove_evaluation_results.nasa.deepseek-coder-6.7b.local.300.trial3.context.json` | `results/scoring/cove_evaluation_results.nasa.deepseek-coder-6.7b.local.300.trial3.context.hallucination_scores.json` |

The quota-limited Google Compute VM was resized to `e2-standard-16`, but its
one-prompt smoke run took 142.53s. The local Mac one-prompt NASA run took
34.62s, so the 12- and 24-prompt NASA benchmarks were run locally. VM advantages
for this workload are reproducibility and offloading long jobs, not speed under
the current project quota.

## Supabase Question Table Runs

The newer Supabase benchmark uses `public.questions`, which contains 500 rows
with the question text plus reference fields: `answer`, `answer_source_field`,
`reference_abstract`, `article_id`, `article_title`, `ntrs_url`, `doi`, and
`source_topics`.

The benchmark exporter now keeps `answer` as `reference_answer` only for
scoring. It is no longer included in any LLM-facing prompt or CoVe context.
Future Supabase question runs provide the article metadata/source context to
direct answering and every factored CoVe step, while hiding the reference answer
until hallucination scoring.

The factored CoVe verification planner is constrained to create only questions
answerable from the supplied source context. Planner outputs that ask for outside
sources, internet/database access, or generic confirmation are filtered before
the verification-answer step.

Question files were exported with `export_supabase_questions.py`:

- `benchmarks/cove_benchmark_questions_supabase_100.json`
- `benchmarks/cove_benchmark_questions_supabase_200.json`
- `benchmarks/cove_benchmark_questions_supabase_300.json`

These runs used local Ollama `deepseek-coder:6.7b`, `max_questions=3`,
`num_predict=768`, skipped `joint_cove`, and used
`--verification-context supabase_questions`. The factored verifier receives the
verification question plus the matching `public.questions` reference row; it
still does not receive the direct baseline answer or draft answer.

Hallucinations were scored with `score_supabase_question_hallucinations.py`.
The scorer uses deterministic checks for simple exact-answer cases and a local
Ollama judge for semantic comparisons against the reference answer, reference
abstract, DOI, NTRS URL, article title, and source topics. Omissions are not
penalized.

Aggregate scores are stored in
`results/scoring/supabase_questions_hallucination_summary.json`.

| Prompt Count | Runtime | Verification Questions | Mode | Score 0 | Score 1 | Score 2 | Any Hallucination Rate | Major Hallucination Rate | Avg Score |
|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|
| 100 | 3856.25s | 289 | Without CoVe (`direct`) | 47 | 52 | 1 | 53.0% | 1.0% | 0.5400 |
| 100 | 3856.25s | 289 | Factored CoVe final | 42 | 54 | 4 | 58.0% | 4.0% | 0.6200 |
| 200 | 7358.23s | 576 | Without CoVe (`direct`) | 94 | 104 | 2 | 53.0% | 1.0% | 0.5400 |
| 200 | 7358.23s | 576 | Factored CoVe final | 98 | 95 | 7 | 51.0% | 3.5% | 0.5450 |
| 300 | 11170.51s | 863 | Without CoVe (`direct`) | 137 | 159 | 4 | 54.3% | 1.3% | 0.5567 |
| 300 | 11170.51s | 863 | Factored CoVe final | 135 | 155 | 10 | 55.0% | 3.3% | 0.5833 |

Across the 100-, 200-, and 300-question runs, there were 600 outputs per mode.
Factored CoVe did not improve the aggregate hallucination rate on this
reference-question benchmark: without CoVe had a 53.7% any-hallucination rate,
while factored CoVe had a 54.2% rate. Major hallucinations increased from 1.2%
without CoVe to 3.5% with factored CoVe. This suggests the current factored
rewrite step can lose or distort answer-table facts even when verification
questions have access to the reference row.

The run artifacts are:

| Prompt Count | Result File | Score File |
|---:|---|---|
| 100 | `results/evaluations/cove_evaluation_results.supabase-questions.deepseek-coder-6.7b.local.100.context.json` | `results/scoring/cove_evaluation_results.supabase-questions.deepseek-coder-6.7b.local.100.context.hallucination_scores.json` |
| 200 | `results/evaluations/cove_evaluation_results.supabase-questions.deepseek-coder-6.7b.local.200.context.json` | `results/scoring/cove_evaluation_results.supabase-questions.deepseek-coder-6.7b.local.200.context.hallucination_scores.json` |
| 300 | `results/evaluations/cove_evaluation_results.supabase-questions.deepseek-coder-6.7b.local.300.context.json` | `results/scoring/cove_evaluation_results.supabase-questions.deepseek-coder-6.7b.local.300.context.hallucination_scores.json` |

### Supabase 10-90 Question Scaling Runs

Additional Supabase `public.questions` runs were completed at 10-question
increments from 10 through 90 questions. These use the same model, CoVe
settings, verification context, and hallucination scorer as the 100/200/300
Supabase question runs above. Aggregate scores are stored in
`results/scoring/supabase_questions_scaled_10_90_hallucination_summary.json`.

| Prompt Count | Runtime | Verification Questions | Mode | Score 0 | Score 1 | Score 2 | Any Hallucination Rate | Major Hallucination Rate | Avg Score |
|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|
| 10 | 362.69s | 28 | Without CoVe (`direct`) | 5 | 5 | 0 | 50.0% | 0.0% | 0.5000 |
| 10 | 362.69s | 28 | Factored CoVe final | 6 | 4 | 0 | 40.0% | 0.0% | 0.4000 |
| 20 | 731.23s | 57 | Without CoVe (`direct`) | 9 | 11 | 0 | 55.0% | 0.0% | 0.5500 |
| 20 | 731.23s | 57 | Factored CoVe final | 8 | 12 | 0 | 60.0% | 0.0% | 0.6000 |
| 30 | 1165.93s | 85 | Without CoVe (`direct`) | 13 | 17 | 0 | 56.7% | 0.0% | 0.5667 |
| 30 | 1165.93s | 85 | Factored CoVe final | 12 | 18 | 0 | 60.0% | 0.0% | 0.6000 |
| 40 | 1453.69s | 115 | Without CoVe (`direct`) | 19 | 21 | 0 | 52.5% | 0.0% | 0.5250 |
| 40 | 1453.69s | 115 | Factored CoVe final | 16 | 24 | 0 | 60.0% | 0.0% | 0.6000 |
| 50 | 1813.53s | 144 | Without CoVe (`direct`) | 22 | 28 | 0 | 56.0% | 0.0% | 0.5600 |
| 50 | 1813.53s | 144 | Factored CoVe final | 20 | 30 | 0 | 60.0% | 0.0% | 0.6000 |
| 60 | 2142.85s | 174 | Without CoVe (`direct`) | 27 | 33 | 0 | 55.0% | 0.0% | 0.5500 |
| 60 | 2142.85s | 174 | Factored CoVe final | 24 | 36 | 0 | 60.0% | 0.0% | 0.6000 |
| 70 | 2473.80s | 203 | Without CoVe (`direct`) | 33 | 37 | 0 | 52.9% | 0.0% | 0.5286 |
| 70 | 2473.80s | 203 | Factored CoVe final | 28 | 42 | 0 | 60.0% | 0.0% | 0.6000 |
| 80 | 2847.47s | 232 | Without CoVe (`direct`) | 39 | 41 | 0 | 51.2% | 0.0% | 0.5125 |
| 80 | 2847.47s | 232 | Factored CoVe final | 33 | 47 | 0 | 58.8% | 0.0% | 0.5875 |
| 90 | 3278.33s | 262 | Without CoVe (`direct`) | 43 | 43 | 4 | 52.2% | 4.4% | 0.5667 |
| 90 | 3278.33s | 262 | Factored CoVe final | 37 | 41 | 12 | 58.9% | 13.3% | 0.7222 |

Across the 10-90 scaling runs, there were 450 outputs per mode. Without CoVe
had a 53.3% any-hallucination rate and a 2.0% major hallucination rate.
Factored CoVe had a 59.1% any-hallucination rate and a 2.7% major
hallucination rate.
