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
- Supabase is wired through the same runner. The direct host
  `db.hcjrjkhqseqozdsfzufm.supabase.co` did not resolve from the local Mac, so
  the next remote test needs the pooler URI from Supabase's Connect panel.

## Next Evaluation Step

Manually score each mode in `cove_evaluation_results.deepseek-coder.local.json`:

- Accuracy: `0=mostly wrong`, `1=mixed`, `2=mostly correct`
- Hallucination: `0=none obvious`, `1=minor/uncertain`, `2=major invented claims`

Those manual labels are the next piece needed before making a research claim about whether CoVe improved answer quality.
