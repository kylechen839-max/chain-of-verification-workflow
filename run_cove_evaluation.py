from __future__ import annotations

from dataclasses import asdict
import argparse
import json
import time
from typing import Any

from cove_workflow import make_ollama_call_llm, run_factored_cove, run_joint_cove


def load_questions(path: str) -> list[dict[str, str]]:
    with open(path, encoding="utf-8") as file:
        questions = json.load(file)

    if not isinstance(questions, list):
        raise ValueError("Benchmark file must contain a JSON array.")

    normalized = []
    for index, item in enumerate(questions, 1):
        if not isinstance(item, dict) or not item.get("question"):
            raise ValueError(f"Benchmark item {index} must be an object with a question.")
        normalized.append(
            {
                "id": str(item.get("id") or f"question-{index}"),
                "category": str(item.get("category") or "uncategorized"),
                "question": str(item["question"]),
            }
        )
    return normalized


def run_timed(label: str, fn: Any) -> dict[str, Any]:
    started = time.time()
    try:
        value = fn()
        error = None
    except Exception as exc:  # noqa: BLE001 - preserve failures in the report.
        value = None
        error = f"{type(exc).__name__}: {exc}"

    return {
        "mode": label,
        "elapsed_seconds": round(time.time() - started, 2),
        "error": error,
        "value": value,
    }


def answer_direct(question: str, call_llm: Any) -> str:
    return call_llm(
        [
            {
                "role": "system",
                "content": "Answer clearly and directly. Keep the response concise but complete.",
            },
            {"role": "user", "content": question},
        ]
    ).strip()


def summarize_value(mode: str, value: Any) -> dict[str, Any]:
    if value is None:
        return {"answer_text": "", "answer_length": 0}

    if mode == "direct":
        text = str(value)
        return {"answer_text": text, "answer_length": len(text)}

    if mode == "joint_cove":
        if isinstance(value, dict):
            text = str(value.get("final") or value.get("raw") or "")
            return {
                "answer_text": text,
                "answer_length": len(text),
                "verification_question_count": len(value.get("verification_questions", []))
                if isinstance(value.get("verification_questions"), list)
                else 0,
                "raw": value,
            }
        text = str(value)
        return {"answer_text": text, "answer_length": len(text), "raw": value}

    if mode == "factored_cove":
        result = asdict(value)
        text = result["final"]
        return {
            "answer_text": text,
            "answer_length": len(text),
            "draft_length": len(result["draft"]),
            "verification_question_count": len(result["verification_questions"]),
            "verification_answer_count": len(result["verification_answers"]),
            "raw": result,
        }

    text = str(value)
    return {"answer_text": text, "answer_length": len(text)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate direct answering vs CoVe modes.")
    parser.add_argument("--model", default="deepseek-coder:1.3b", help="Ollama model name.")
    parser.add_argument("--host", default="http://127.0.0.1:11434", help="Ollama host URL.")
    parser.add_argument("--questions", default="cove_benchmark_questions.json")
    parser.add_argument("--output", default="cove_evaluation_results.local.json")
    parser.add_argument("--max-questions", type=int, default=2)
    parser.add_argument("--num-predict", type=int, default=512)
    parser.add_argument("--limit", type=int, default=0, help="Limit benchmark questions; 0 means all.")
    parser.add_argument("--skip-joint", action="store_true", help="Skip one-call joint CoVe mode.")
    args = parser.parse_args()

    call_llm = make_ollama_call_llm(
        model=args.model,
        host=args.host,
        think=False,
        options={"num_predict": args.num_predict},
    )
    questions = load_questions(args.questions)
    if args.limit:
        questions = questions[: args.limit]

    report: dict[str, Any] = {
        "model": args.model,
        "host": args.host,
        "max_questions": args.max_questions,
        "num_predict": args.num_predict,
        "question_file": args.questions,
        "manual_scoring_scale": {
            "accuracy": "0=mostly wrong, 1=mixed or partially correct, 2=mostly correct",
            "hallucination": "0=none obvious, 1=minor/uncertain, 2=major invented claims",
        },
        "results": [],
    }

    for item in questions:
        print(f"Question {item['id']}: {item['question']}")
        modes = [
            ("direct", lambda q=item["question"]: answer_direct(q, call_llm)),
        ]
        if not args.skip_joint:
            modes.append(
                (
                    "joint_cove",
                    lambda q=item["question"]: run_joint_cove(
                        q,
                        call_llm=call_llm,
                        max_questions=args.max_questions,
                    ),
                )
            )
        modes.append(
            (
                "factored_cove",
                lambda q=item["question"]: run_factored_cove(
                    q,
                    call_llm=call_llm,
                    max_questions=args.max_questions,
                ),
            )
        )

        mode_results = []
        for mode, fn in modes:
            timed = run_timed(mode, fn)
            summary = summarize_value(mode, timed.pop("value"))
            mode_results.append(
                {
                    **timed,
                    **summary,
                    "manual_accuracy_score": None,
                    "manual_hallucination_score": None,
                    "manual_notes": "",
                }
            )
            print(
                f"  {mode}: {mode_results[-1]['elapsed_seconds']}s, "
                f"{mode_results[-1].get('verification_question_count', 0)} checks, "
                f"{mode_results[-1]['answer_length']} chars"
            )

        report["results"].append({**item, "modes": mode_results})

    with open(args.output, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
