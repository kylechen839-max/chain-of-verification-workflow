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
