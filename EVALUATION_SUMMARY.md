# CoVe Evaluation Summary

Latest local benchmark:

```bash
python3 run_cove_evaluation.py \
  --model deepseek-coder:1.3b \
  --max-questions 2 \
  --num-predict 512 \
  --output cove_evaluation_results.deepseek-coder.local.json
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

The NASA prompt file `cove_benchmark_questions_nasa_30.json` was generated from
`public.nasa_articles`. Each prompt includes only article metadata/abstract
facts and instructs the model not to add outside facts.

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

Run 16 was scanned for the earlier failure modes across all 72 verification
answers: 0 database-access refusals, 0 draft-dependent verification questions,
and 0 flagged speculative answers.

The quota-limited Google Compute VM was resized to `e2-standard-16`, but its
one-prompt smoke run took 142.53s. The local Mac one-prompt NASA run took
34.62s, so the 12- and 24-prompt NASA benchmarks were run locally. VM advantages
for this workload are reproducibility and offloading long jobs, not speed under
the current project quota.

## Next Evaluation Step

Manually score each mode in `cove_evaluation_results.deepseek-coder.local.json`:

- Accuracy: `0=mostly wrong`, `1=mixed`, `2=mostly correct`
- Hallucination: `0=none obvious`, `1=minor/uncertain`, `2=major invented claims`

Those manual labels are the next piece needed before making a research claim about whether CoVe improved answer quality.
