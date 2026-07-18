from __future__ import annotations

from dataclasses import asdict
import argparse
import json
import re
import time
from typing import Any

from cove_workflow import make_ollama_call_llm, run_factored_cove, run_joint_cove
from cove_result_store import database_schema_from_env, database_url_from_env, save_report


def load_questions(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as file:
        questions = json.load(file)

    if not isinstance(questions, list):
        raise ValueError("Benchmark file must contain a JSON array.")

    normalized = []
    for index, item in enumerate(questions, 1):
        if not isinstance(item, dict) or not item.get("question"):
            raise ValueError(f"Benchmark item {index} must be an object with a question.")
        normalized_item = dict(item)
        normalized_item["id"] = str(item.get("id") or f"question-{index}")
        normalized_item["category"] = str(item.get("category") or "uncategorized")
        normalized_item["question"] = str(item["question"])
        normalized.append(normalized_item)
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


def extract_nasa_article_id(text: str) -> str | None:
    match = re.search(r"NASA article id:\s*(\d+)", text)
    if match:
        return match.group(1)
    match = re.search(r"\bnasa-(\d+)\b", text, flags=re.IGNORECASE)
    return match.group(1) if match else None


def build_nasa_context_provider(database_url: str | None) -> Any:
    if not database_url:
        return None

    try:
        import psycopg
    except ImportError:
        return None

    cache: dict[str, str] = {}

    def join_list(value: Any) -> str:
        if isinstance(value, list):
            return ", ".join(str(item) for item in value) or "Not listed"
        return str(value or "Not listed")

    def fetch_context(article_id: str) -> str:
        if article_id in cache:
            return cache[article_id]

        query = """
        select id, title, abstract, author_names, keywords, subject_categories,
               center_name, center_code, sti_type, distribution, distribution_date,
               submitted_date, created_date, modified_date, publication_name,
               publication_date, publisher, volume, issue, doi, report_numbers,
               pdf_url, fulltext_url, downloads_available, ntrs_url, source_topics
        from public.nasa_articles
        where id = %s
        """
        with psycopg.connect(
            database_url, connect_timeout=15, prepare_threshold=None
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(query, (article_id,))
                row = cur.fetchone()
                if not row:
                    cache[article_id] = ""
                    return ""
                cols = [desc.name for desc in cur.description]

        record = dict(zip(cols, row))
        lines = [
            f"NASA article id: {record['id']}",
            f"Title: {record['title']}",
            f"Abstract: {record['abstract'] or 'Not listed'}",
            f"Authors: {join_list(record['author_names'])}",
            f"Keywords: {join_list(record['keywords'])}",
            f"Subject categories: {join_list(record['subject_categories'])}",
            f"NASA center: {record['center_name'] or 'Not listed'} ({record['center_code'] or 'not listed'})",
            f"STI type: {record['sti_type'] or 'Not listed'}",
            f"Distribution: {record['distribution'] or 'Not listed'}",
            f"Distribution date: {record['distribution_date'] or 'Not listed'}",
            f"Submitted date: {record['submitted_date'] or 'Not listed'}",
            f"Created date: {record['created_date'] or 'Not listed'}",
            f"Modified date: {record['modified_date'] or 'Not listed'}",
            f"Publication: {record['publication_name'] or 'Not listed'}",
            f"Publication date: {record['publication_date'] or 'Not listed'}",
            f"Publisher: {record['publisher'] or 'Not listed'}",
            f"Volume: {record['volume'] or 'Not listed'}",
            f"Issue: {record['issue'] or 'Not listed'}",
            f"DOI: {record['doi'] or 'Not listed'}",
            f"Report numbers: {join_list(record['report_numbers'])}",
            f"PDF URL: {record['pdf_url'] or 'Not listed'}",
            f"Fulltext URL: {record['fulltext_url'] or 'Not listed'}",
            f"Downloads available: {record['downloads_available']}",
            f"NTRS URL: {record['ntrs_url'] or 'Not listed'}",
            f"Source topics: {join_list(record['source_topics'])}",
        ]
        cache[article_id] = "\n".join(lines)
        return cache[article_id]

    def context_provider(original_question: str, verification_question: str) -> str:
        del verification_question
        article_id = extract_nasa_article_id(original_question)
        return fetch_context(article_id) if article_id else ""

    return context_provider


def extract_supabase_question_id(text: str) -> int | None:
    match = re.search(r"Supabase question id:\s*(\d+)", text, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    match = re.search(r"\bsupabase-question-(\d+)\b", text, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def build_supabase_question_context_provider(database_url: str | None) -> Any:
    if not database_url:
        return None

    try:
        import psycopg
    except ImportError:
        return None

    cache: dict[int, str] = {}

    def join_list(value: Any) -> str:
        if isinstance(value, list):
            return ", ".join(str(item) for item in value) or "Not listed"
        return str(value or "Not listed")

    def normalize_missing(value: Any) -> str:
        if value is None:
            return "Not listed"
        text = str(value).strip()
        return "Not listed" if not text or text.lower() == "none" else text

    def fetch_context(qid: int) -> str:
        if qid in cache:
            return cache[qid]

        query = """
        select q.qid, q.complexity, q.type, q.question, q.answer_source_field,
               q.reference_abstract, q.article_id, q.article_title, q.ntrs_url,
               q.doi, q.source_topics,
               a.abstract, a.author_names, a.keywords, a.subject_categories,
               a.center_name, a.center_code, a.sti_type, a.publication_name,
               a.publication_date, a.distribution_date, a.report_numbers
        from public.questions q
        left join public.nasa_articles a on a.id = q.article_id
        where q.qid = %s
        """
        with psycopg.connect(
            database_url, connect_timeout=15, prepare_threshold=None
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(query, (qid,))
                row = cur.fetchone()
                if not row:
                    cache[qid] = ""
                    return ""
                cols = [desc.name for desc in cur.description]

        record = dict(zip(cols, row))
        lines = [
            f"Supabase question id: {record['qid']}",
            f"Question complexity: {record['complexity']}",
            f"Question type: {record['type']}",
            f"Question: {record['question']}",
            f"Requested source field: {normalize_missing(record['answer_source_field'])}",
            f"Reference abstract: {normalize_missing(record['reference_abstract'])}",
            f"Article id: {record['article_id']}",
            f"Article title: {normalize_missing(record['article_title'])}",
            f"Article abstract: {normalize_missing(record['abstract'])}",
            f"Authors: {join_list(record['author_names'])}",
            f"Keywords: {join_list(record['keywords'])}",
            f"Subject categories: {join_list(record['subject_categories'])}",
            f"NASA center: {normalize_missing(record['center_name'])} ({normalize_missing(record['center_code'])})",
            f"STI type: {normalize_missing(record['sti_type'])}",
            f"Publication: {normalize_missing(record['publication_name'])}",
            f"Publication date: {normalize_missing(record['publication_date'])}",
            f"Distribution date: {normalize_missing(record['distribution_date'])}",
            f"Report numbers: {join_list(record['report_numbers'])}",
            f"NTRS URL: {normalize_missing(record['ntrs_url'])}",
            f"DOI: {normalize_missing(record['doi'])}",
            f"Source topics: {join_list(record['source_topics'])}",
        ]
        cache[qid] = "\n".join(lines)
        return cache[qid]

    def context_provider(original_question: str, verification_question: str) -> str:
        del verification_question
        qid = extract_supabase_question_id(original_question)
        return fetch_context(qid) if qid else ""

    return context_provider


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
    try:
        from dotenv import load_dotenv

        load_dotenv(".env")
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="Evaluate direct answering vs CoVe modes.")
    parser.add_argument("--model", default="deepseek-coder:1.3b", help="Ollama model name.")
    parser.add_argument("--host", default="http://127.0.0.1:11434", help="Ollama host URL.")
    parser.add_argument("--questions", default="benchmarks/cove_benchmark_questions.json")
    parser.add_argument("--output", default="results/evaluations/cove_evaluation_results.local.json")
    parser.add_argument("--max-questions", type=int, default=2)
    parser.add_argument("--num-predict", type=int, default=512)
    parser.add_argument("--limit", type=int, default=0, help="Limit benchmark questions; 0 means all.")
    parser.add_argument("--skip-joint", action="store_true", help="Skip one-call joint CoVe mode.")
    parser.add_argument(
        "--verification-context",
        choices=["none", "auto", "nasa", "supabase_questions"],
        default="auto",
        help="Context source for factored CoVe verification answers.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help=(
            "Optional result database URL. Defaults to COVE_DATABASE_URL, "
            "SUPABASE_DATABASE_URL, or DATABASE_URL when set."
        ),
    )
    parser.add_argument(
        "--database-schema",
        default=None,
        help="Postgres/Supabase schema for confined result tables. Defaults to COVE_DATABASE_SCHEMA or cove_test.",
    )
    parser.add_argument(
        "--skip-db-init",
        action="store_true",
        help="Skip schema/table creation for database writes when tables already exist.",
    )
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
    database_url = args.database_url or database_url_from_env()
    nasa_context_provider = (
        build_nasa_context_provider(database_url)
        if args.verification_context in {"auto", "nasa"}
        else None
    )
    supabase_question_context_provider = (
        build_supabase_question_context_provider(database_url)
        if args.verification_context in {"auto", "supabase_questions"}
        else None
    )

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
                lambda q=item["question"], item_id=item["id"]: run_factored_cove(
                    q,
                    call_llm=call_llm,
                    max_questions=args.max_questions,
                    context_provider=(
                        supabase_question_context_provider
                        if supabase_question_context_provider
                        and (
                            args.verification_context == "supabase_questions"
                            or item_id.startswith("supabase-question-")
                            or extract_supabase_question_id(q)
                        )
                        else nasa_context_provider
                        if nasa_context_provider
                        and (
                            args.verification_context == "nasa"
                            or item_id.startswith("nasa-")
                            or extract_nasa_article_id(q)
                        )
                        else None
                    ),
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

    if database_url:
        run_id = save_report(
            database_url,
            report,
            schema=args.database_schema or database_schema_from_env(),
            initialize=not args.skip_db_init,
        )
        print(f"Wrote database run_id {run_id}")


if __name__ == "__main__":
    main()
