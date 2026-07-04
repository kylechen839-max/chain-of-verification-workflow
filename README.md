# Chain of Verification Workflow

This project recreates a Chain of Verification workflow in Python and Jupyter.

The workflow:

1. Drafts an initial answer.
2. Generates verification questions from the draft.
3. Answers each verification question independently, without showing the draft.
4. Rewrites the final answer using the verification answers.

## Files

- `Untitled-1.ipynb` - notebook for running the workflow.
- `cove_workflow.py` - reusable Python implementation.
- `requirements.txt` - Python dependencies.

## Setup

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Create a `.env` file in this folder:

```text
OPENAI_API_KEY=your-api-key-here
```

Do not commit or share `.env`.

## Run

Open `Untitled-1.ipynb` in VS Code or Jupyter, select the Python environment where the dependencies are installed, and run the cells from top to bottom.

To reduce API calls while testing, set:

```python
MAX_QUESTIONS = 2
```

## Ollama Tests

Ollama can run local/open models, but it cannot run proprietary ChatGPT models directly.
For an OpenAI open-weight model on Ollama, use `gpt-oss:20b` or `gpt-oss:120b`
on hardware with enough memory. For quick CPU tests, this project uses
`llama3.2:1b`.

Install and pull a small test model:

```bash
ollama pull llama3.2:1b
```

Run the CoVe test suite:

```bash
python3 run_ollama_cove_tests.py \
  --model llama3.2:1b \
  --max-questions 2 \
  --output ollama_cove_test_results.local.json
```

You can also run a DeepSeek model through Ollama. `deepseek-r1` is a reasoning
model and can spend a long time in thinking mode, so the adapter disables
thinking by default and strips `<think>` blocks from saved output. For a small
CPU-friendly DeepSeek run, use `deepseek-coder:1.3b` with coding-domain
questions:

```bash
ollama pull deepseek-coder:1.3b
python3 run_ollama_cove_tests.py \
  --model deepseek-coder:1.3b \
  --max-questions 2 \
  --num-predict 512 \
  --output ollama_cove_test_results.deepseek-coder.local.json \
  --question "Give a concise history of the Python programming language, including creator, first release year, and major version milestones." \
  --question "Explain Git core workflow, including clone, branch, commit, merge, and push."
```

If your machine has enough memory for OpenAI's open-weight Ollama model:

```bash
ollama pull gpt-oss:20b
python3 run_ollama_cove_tests.py --model gpt-oss:20b --max-questions 2
```

## Google Compute Engine Test

The same test runner can run on a Google Compute Engine VM after installing
Ollama and copying the project files:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:1b
python3 run_ollama_cove_tests.py \
  --model llama3.2:1b \
  --max-questions 2 \
  --output ollama_cove_test_results.gce.json
```

The checked-in result files show one local run and one Google Compute Engine run.
The DeepSeek Coder tests ran successfully on the existing `e2-standard-8`
CPU-only VM, so no VM resize was required.

For the current small Ollama models, the local Mac is faster than the CPU-only
Google Compute VM. Prefer local runs for iterative testing, and use the VM only
when cloud reproducibility or different hardware is specifically needed.

## CoVe Evaluation

Run the fixed benchmark to compare direct answers, joint CoVe, and factored CoVe:

```bash
python3 run_cove_evaluation.py \
  --model deepseek-coder:1.3b \
  --max-questions 2 \
  --num-predict 512 \
  --output cove_evaluation_results.deepseek-coder.local.json
```

The benchmark questions live in `cove_benchmark_questions.json`. The latest
local benchmark summary is in `EVALUATION_SUMMARY.md`.

The JSON output includes placeholders for manual accuracy and hallucination
scores. Fill those in after reviewing each answer if you want to make a
research-style comparison between direct answers and CoVe answers.

## NASA Article Evaluation

`cove_benchmark_questions_nasa_30.json` contains 30 prompts generated from the
Supabase `public.nasa_articles` table populated by
`Rohan-Gambhir/Hallucinations`. The table stores NASA NTRS article metadata and
abstracts for black holes and gravitational waves.

Run a NASA benchmark with direct baseline and factored CoVe only:

```bash
python3 run_cove_evaluation.py \
  --model deepseek-coder:6.7b \
  --questions cove_benchmark_questions_nasa_30.json \
  --limit 24 \
  --max-questions 3 \
  --num-predict 768 \
  --output cove_evaluation_results.nasa.deepseek-coder-6.7b.local.24.context.json \
  --database-schema cove_test \
  --skip-db-init \
  --skip-joint \
  --verification-context nasa
```

Use `--skip-joint` when testing the strict factored CoVe safeguard. In factored
CoVe, verification answers receive only the self-contained verification
question plus retrieved NASA article context, not the draft or direct baseline
response. The NASA context comes from `public.nasa_articles` and is saved in
the raw result payload as `verification_contexts` for audit.

The verification-answer prompt uses this grounding instruction:

```text
Use the following pieces of context to answer the question. If you don't know the answer, just say that you don't know; don't try to make up an answer.
```

## Confined Database Results

For a local confined database test, write results into a SQLite file:

```bash
python3 run_cove_evaluation.py \
  --model deepseek-coder:1.3b \
  --limit 1 \
  --max-questions 2 \
  --num-predict 512 \
  --output cove_evaluation_results.confined.smoke.json \
  --database-url sqlite:///cove_results.confined.local.db
```

For Supabase, set the pooled Postgres connection string in `.env`:

```text
SUPABASE_DATABASE_URL=postgresql://postgres.hcjrjkhqseqozdsfzufm:password@aws-...supabase.com:6543/postgres
COVE_DATABASE_SCHEMA=cove_test
```

Command-line evaluation runs load `.env` automatically. If the direct
`db.<project-ref>.supabase.co` hostname does not resolve, copy the pooler URI
from Supabase's Connect panel instead.

Then run:

```bash
python3 run_cove_evaluation.py \
  --model deepseek-coder:1.3b \
  --max-questions 2 \
  --num-predict 512 \
  --output cove_evaluation_results.supabase.json \
  --database-schema cove_test
```

The runner creates `cove_test.cove_evaluation_runs` and
`cove_test.cove_evaluation_results`, keeping benchmark rows isolated from the
rest of the database.

If the schema already exists and your database user cannot create schemas, add
`--skip-db-init` to write into the existing tables.

If database password auth is unavailable, you can sync an existing JSON report
through the Supabase Management API:

```bash
python3 sync_cove_report_to_supabase.py \
  cove_evaluation_results.deepseek-coder-6.7b.full.local.json \
  --project-ref hcjrjkhqseqozdsfzufm \
  --schema cove_test
```

For direct temporary Postgres writes, create a Supabase CLI login role through
the Management API, use the pooler username format
`cli_login_postgres.<project-ref>`, and run with `--skip-db-init` after the
`cove_test` tables already exist.
