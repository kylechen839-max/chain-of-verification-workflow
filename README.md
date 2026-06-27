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
