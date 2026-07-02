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

## Next Evaluation Step

Manually score each mode in `cove_evaluation_results.deepseek-coder.local.json`:

- Accuracy: `0=mostly wrong`, `1=mixed`, `2=mostly correct`
- Hallucination: `0=none obvious`, `1=minor/uncertain`, `2=major invented claims`

Those manual labels are the next piece needed before making a research claim about whether CoVe improved answer quality.
