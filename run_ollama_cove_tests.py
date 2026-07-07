from __future__ import annotations

from dataclasses import asdict
import argparse
import json
import time

from cove_workflow import make_ollama_call_llm, run_factored_cove


TEST_QUESTIONS = [
    "Give a concise biography of Grace Hopper, including major dates and accomplishments.",
    "Summarize Apollo 11, including dates, astronauts, and major mission events.",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Chain of Verification tests with Ollama.")
    parser.add_argument("--model", default="llama3.2:1b", help="Ollama model name.")
    parser.add_argument("--host", default="http://127.0.0.1:11434", help="Ollama host URL.")
    parser.add_argument("--max-questions", type=int, default=2, help="Verification questions per run.")
    parser.add_argument(
        "--num-predict",
        type=int,
        default=512,
        help="Maximum generated tokens per Ollama call.",
    )
    parser.add_argument(
        "--think",
        action="store_true",
        help="Enable model thinking output for Ollama models that support it.",
    )
    parser.add_argument(
        "--question",
        action="append",
        dest="questions",
        help="Question to test. Pass multiple times for multiple tests.",
    )
    parser.add_argument(
        "--output",
        default="results/ollama/ollama_cove_test_results.json",
        help="JSON output path.",
    )
    args = parser.parse_args()

    call_llm = make_ollama_call_llm(
        model=args.model,
        host=args.host,
        think=args.think,
        options={"num_predict": args.num_predict},
    )
    results = []

    questions = args.questions or TEST_QUESTIONS

    for question in questions:
        started = time.time()
        result = run_factored_cove(
            question=question,
            call_llm=call_llm,
            max_questions=args.max_questions,
        )
        elapsed_seconds = round(time.time() - started, 2)
        results.append(
            {
                "model": args.model,
                "host": args.host,
                "think": args.think,
                "num_predict": args.num_predict,
                "elapsed_seconds": elapsed_seconds,
                **asdict(result),
            }
        )
        print(f"Finished: {question[:60]}... ({elapsed_seconds}s)")
        print(result.final)
        print()

    with open(args.output, "w", encoding="utf-8") as file:
        json.dump(results, file, indent=2)

    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
