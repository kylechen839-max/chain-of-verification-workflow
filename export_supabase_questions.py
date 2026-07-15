from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def database_url_from_env() -> str:
    for name in ("SUPABASE_DATABASE_URL", "COVE_DATABASE_URL", "DATABASE_URL"):
        value = os.environ.get(name)
        if value:
            return value
    raise RuntimeError("Set SUPABASE_DATABASE_URL, COVE_DATABASE_URL, or DATABASE_URL.")


def normalize_missing(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return None if not text or text.lower() == "none" else text


def build_prompt(row: dict[str, Any]) -> str:
    lines = [
        "Answer the question using only the provided source fields.",
        "If the source fields do not contain enough information, say that you don't know.",
        "Do not add outside facts.",
        "",
        f"Supabase question id: {row['qid']}",
        f"Question: {row['question']}",
        f"Question type: {row['type']}",
        f"Question complexity: {row['complexity']}",
        f"Article id: {row['article_id']}",
        f"Article title: {normalize_missing(row['article_title']) or 'Not listed'}",
        f"Reference answer: {normalize_missing(row['answer']) or 'Not listed'}",
        f"Answer source field: {normalize_missing(row['answer_source_field']) or 'Not listed'}",
        f"Reference abstract: {normalize_missing(row['reference_abstract']) or 'Not listed'}",
        f"NTRS URL: {normalize_missing(row['ntrs_url']) or 'Not listed'}",
        f"DOI: {normalize_missing(row['doi']) or 'Not listed'}",
        "Source topics: "
        + (
            ", ".join(str(item) for item in row["source_topics"])
            if isinstance(row["source_topics"], list)
            else str(row["source_topics"] or "Not listed")
        ),
    ]
    return "\n".join(lines)


def main() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(".env")
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="Export Supabase public.questions benchmark rows.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()

    import psycopg

    query = """
    select qid, complexity, type, question, answer, answer_source_field,
           reference_abstract, article_id, article_title, ntrs_url, doi,
           source_topics, inserted_at
    from public.questions
    order by qid
    limit %s offset %s
    """
    database_url = args.database_url or database_url_from_env()
    with psycopg.connect(database_url, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute(query, (args.limit, args.offset))
            rows = cur.fetchall()
            cols = [desc.name for desc in cur.description]

    items = []
    for row in rows:
        record = dict(zip(cols, row))
        item = {
            "id": f"supabase-question-{record['qid']}",
            "category": f"supabase-question-{record['type']}",
            "question": build_prompt(record),
            "source_table": "public.questions",
            "qid": record["qid"],
            "complexity": record["complexity"],
            "type": record["type"],
            "source_question": record["question"],
            "reference_answer": normalize_missing(record["answer"]),
            "answer_source_field": normalize_missing(record["answer_source_field"]),
            "reference_abstract": normalize_missing(record["reference_abstract"]),
            "article_id": str(record["article_id"]),
            "article_title": normalize_missing(record["article_title"]),
            "ntrs_url": normalize_missing(record["ntrs_url"]),
            "doi": normalize_missing(record["doi"]),
            "source_topics": record["source_topics"],
            "inserted_at": str(record["inserted_at"]) if record["inserted_at"] else None,
        }
        items.append(item)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(items, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Wrote {len(items)} questions to {output}")


if __name__ == "__main__":
    main()
