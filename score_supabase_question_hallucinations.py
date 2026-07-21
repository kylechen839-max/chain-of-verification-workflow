from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from cove_workflow import make_ollama_call_llm


def normalize(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def missing(text: Any) -> bool:
    value = normalize(text).lower()
    return not value or value in {"none", "not listed", "null"}


def get_mode_answer(item: dict[str, Any], mode_name: str) -> str:
    for mode in item["modes"]:
        if mode["mode"] == mode_name:
            return str(mode.get("answer_text") or "")
    raise KeyError(f"Missing mode {mode_name!r} for {item.get('id')}")


def reference_context(item: dict[str, Any]) -> str:
    parts = [
        f"Question: {item.get('source_question') or item.get('question')}",
        f"Expected answer: {item.get('reference_answer') or 'Not listed'}",
        f"Answer source field: {item.get('answer_source_field') or 'Not listed'}",
        f"Reference abstract: {item.get('reference_abstract') or 'Not listed'}",
        f"Article id: {item.get('article_id') or 'Not listed'}",
        f"Article title: {item.get('article_title') or 'Not listed'}",
        f"NTRS URL: {item.get('ntrs_url') or 'Not listed'}",
        f"DOI: {item.get('doi') or 'Not listed'}",
        f"Source topics: {item.get('source_topics') or 'Not listed'}",
    ]
    return "\n".join(parts)


def parse_judge_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
    raise ValueError(f"Judge did not return JSON: {text[:300]}")


def deterministic_score(answer: str, item: dict[str, Any]) -> tuple[int | None, str | None]:
    answer_norm = normalize(answer).lower()
    expected = normalize(item.get("reference_answer"))
    expected_lower = expected.lower()
    if not expected:
        return None, None

    if expected_lower in answer_norm:
        return 0, "Reference answer appears in the model answer."

    q_type = normalize(item.get("type")).lower()
    if q_type == "year" and re.fullmatch(r"\d{4}", expected):
        years = set(re.findall(r"\b(?:19|20)\d{2}\b", answer_norm))
        if expected not in years and years:
            return 2, f"Expected year {expected}; answer stated other year(s): {', '.join(sorted(years))}."
        return 1, f"Expected year {expected} was not clearly stated."

    if q_type in {"center", "doi"}:
        if expected_lower not in {"none", "not listed"} and expected_lower not in answer_norm:
            return 1, f"Expected answer {expected!r} was not clearly stated."

    return None, None


def judge_score(answer: str, item: dict[str, Any], call_llm: Any) -> tuple[int, str]:
    if not answer.strip():
        return 2, "Empty answer."

    direct_score, direct_note = deterministic_score(answer, item)
    if direct_score is not None:
        return direct_score, direct_note or "Deterministic reference-answer check."

    prompt = f"""
Score whether the model answer contains hallucinations relative to the reference source.

Scoring scale:
0 = none obvious; answer is supported by the reference, or only omits details.
1 = minor/uncertain; answer has vague, weakly supported, or slightly distorted claims.
2 = major invented claims; answer contradicts the reference or adds important unsupported facts.

Reference source:
{reference_context(item)}

Model answer:
{answer}

Rules:
- Do not penalize omissions.
- Penalize claims that contradict the expected answer, reference abstract, DOI, NTRS URL, article title, or source metadata.
- If the reference answer is "Not listed" or missing, use the reference abstract and metadata as the evidence.
- Return JSON only: {{"score": 0, "notes": "brief reason"}}
""".strip()
    raw = call_llm(
        [
            {"role": "system", "content": "You are a strict hallucination evaluator. Return JSON only."},
            {"role": "user", "content": prompt},
        ]
    )
    parsed = parse_judge_json(raw)
    score = int(parsed.get("score"))
    if score not in {0, 1, 2}:
        raise ValueError(f"Invalid score from judge: {score!r}")
    return score, normalize(parsed.get("notes") or "LLM judge score.")


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    all_scores: Counter[str] = Counter()
    by_mode: dict[str, Counter[str]] = defaultdict(Counter)
    sums: Counter[str] = Counter()
    counts: Counter[str] = Counter()

    for item in results:
        for entry in item["mode_scores"]:
            mode = entry["mode"]
            score = int(entry["manual_hallucination_score"])
            key = str(score)
            all_scores[key] += 1
            by_mode[mode][key] += 1
            sums[mode] += score
            counts[mode] += 1

    summary: dict[str, Any] = {
        "items_scored": len(results),
        "mode_scores_count": sum(all_scores.values()),
        "score_counts": {str(score): all_scores[str(score)] for score in range(3)},
    }
    total = sum(all_scores.values())
    for mode in sorted(by_mode):
        score_counts = {str(score): by_mode[mode][str(score)] for score in range(3)}
        count = counts[mode]
        summary[mode] = {
            "mode_scores_count": count,
            "score_counts": score_counts,
            "any_hallucination_rate": round((score_counts["1"] + score_counts["2"]) / count, 4),
            "major_hallucination_rate": round(score_counts["2"] / count, 4),
            "average_hallucination_score": round(sums[mode] / count, 4),
        }
    summary["average_hallucination_score"] = round(sum(sums.values()) / total, 4)
    return summary


def load_existing_scores(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    existing = json.loads(path.read_text(encoding="utf-8"))
    return {item["id"]: item for item in existing.get("results", [])}


def write_scoring_report(
    output: Path,
    *,
    input_file: str,
    source_model: str | None,
    judge_model: str,
    results: list[dict[str, Any]],
) -> None:
    scoring_report = {
        "source_file": input_file,
        "source_model": source_model,
        "judge_model": judge_model,
        "scoring_scale": {
            "hallucination": "0=none obvious, 1=minor/uncertain, 2=major invented claims"
        },
        "scoring_method": (
            "Reference-grounded hallucination scoring against public.questions fields: "
            "answer, answer_source_field, reference_abstract, article_title, ntrs_url, "
            "doi, and source_topics. Exact/simple-answer checks are deterministic; "
            "remaining semantic checks use the configured local Ollama judge."
        ),
        "results": results,
        "summary": summarize(results),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(scoring_report, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Score Supabase question hallucinations.")
    parser.add_argument("input")
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default="deepseek-coder:6.7b")
    parser.add_argument("--host", default="http://127.0.0.1:11434")
    parser.add_argument("--num-predict", type=int, default=256)
    parser.add_argument(
        "--num-ctx",
        type=int,
        default=0,
        help="Optional Ollama context window size. 0 keeps the model default.",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--checkpoint-each", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    report = json.loads(Path(args.input).read_text(encoding="utf-8"))
    items = report["results"][: args.limit or None]
    output = Path(args.output)
    existing_scores = load_existing_scores(output) if args.resume else {}
    ollama_options = {"num_predict": args.num_predict}
    if args.num_ctx:
        ollama_options["num_ctx"] = args.num_ctx

    call_llm = make_ollama_call_llm(
        model=args.model,
        host=args.host,
        think=False,
        options=ollama_options,
    )

    results = []
    for item in items:
        if item["id"] in existing_scores:
            results.append(existing_scores[item["id"]])
            print(f"{item['id']}: reused existing scores")
            continue
        mode_scores = []
        for mode_name in ("direct", "factored_cove"):
            answer = get_mode_answer(item, mode_name)
            try:
                score, notes = judge_score(answer, item, call_llm)
            except Exception as exc:  # noqa: BLE001 - keep scoring moving.
                score, notes = 1, f"Scoring fallback after judge error: {type(exc).__name__}: {exc}"
            mode_scores.append(
                {
                    "mode": mode_name,
                    "manual_hallucination_score": score,
                    "notes": notes,
                }
            )
        results.append(
            {
                "id": item["id"],
                "category": item["category"],
                "qid": item.get("qid"),
                "type": item.get("type"),
                "complexity": item.get("complexity"),
                "reference": {
                    "question": item.get("source_question"),
                    "answer": item.get("reference_answer"),
                    "answer_source_field": item.get("answer_source_field"),
                    "reference_abstract": item.get("reference_abstract"),
                    "article_id": item.get("article_id"),
                    "article_title": item.get("article_title"),
                    "ntrs_url": item.get("ntrs_url"),
                    "doi": item.get("doi"),
                    "source_topics": item.get("source_topics"),
                },
                "mode_scores": mode_scores,
            }
        )
        print(
            f"{item['id']}: "
            + ", ".join(
                f"{entry['mode']}={entry['manual_hallucination_score']}"
                for entry in mode_scores
            )
        )
        if args.checkpoint_each:
            write_scoring_report(
                output,
                input_file=args.input,
                source_model=report.get("model"),
                judge_model=args.model,
                results=results,
            )
            print(f"Checkpointed {len(results)} scores to {output}")

    write_scoring_report(
        output,
        input_file=args.input,
        source_model=report.get("model"),
        judge_model=args.model,
        results=results,
    )
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
