from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from typing import Any

from cove_result_store import POSTGRES_SCHEMA_SQL, database_schema_from_env, validate_identifier


def load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(".env")
    except ImportError:
        pass


def sql_literal(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def post_query(project_ref: str, token: str, query: str) -> Any:
    request = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{project_ref}/database/query",
        data=json.dumps({"query": query}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "supabase-cli/2.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase query failed: {error.code} {detail}") from error

    return json.loads(text) if text else None


def ensure_schema(project_ref: str, token: str, schema: str) -> None:
    post_query(project_ref, token, f"create schema if not exists {schema};")
    post_query(project_ref, token, POSTGRES_SCHEMA_SQL.format(schema=schema))


def insert_report(project_ref: str, token: str, schema: str, report: dict[str, Any]) -> int:
    metadata_json = json.dumps(
        {"manual_scoring_scale": report.get("manual_scoring_scale", {})},
        ensure_ascii=True,
    )
    run_rows = post_query(
        project_ref,
        token,
        f"""
        insert into {schema}.cove_evaluation_runs (
            model, host, question_file, max_questions, num_predict,
            result_count, metadata_json
        )
        values (
            {sql_literal(report["model"])},
            {sql_literal(report["host"])},
            {sql_literal(report["question_file"])},
            {int(report["max_questions"])},
            {int(report["num_predict"])},
            {len(report["results"])},
            {sql_literal(metadata_json)}::jsonb
        )
        returning id;
        """,
    )
    run_id = int(run_rows[0]["id"])

    for item in report["results"]:
        for mode_result in item["modes"]:
            payload_json = json.dumps(mode_result, ensure_ascii=True)
            post_query(
                project_ref,
                token,
                f"""
                insert into {schema}.cove_evaluation_results (
                    run_id, question_id, category, question, mode,
                    elapsed_seconds, error, answer_length,
                    verification_question_count, manual_accuracy_score,
                    manual_hallucination_score, manual_notes, payload_json
                )
                values (
                    {run_id},
                    {sql_literal(item["id"])},
                    {sql_literal(item["category"])},
                    {sql_literal(item["question"])},
                    {sql_literal(mode_result["mode"])},
                    {float(mode_result["elapsed_seconds"])},
                    {sql_literal(mode_result.get("error"))},
                    {int(mode_result.get("answer_length") or 0)},
                    {int(mode_result.get("verification_question_count") or 0)},
                    {sql_literal(mode_result.get("manual_accuracy_score"))},
                    {sql_literal(mode_result.get("manual_hallucination_score"))},
                    {sql_literal(mode_result.get("manual_notes", ""))},
                    {sql_literal(payload_json)}::jsonb
                );
                """,
            )

    return run_id


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Sync a CoVe JSON report to Supabase.")
    parser.add_argument("report")
    parser.add_argument("--project-ref", default=os.environ.get("SUPABASE_PROJECT_REF"))
    parser.add_argument("--schema", default=database_schema_from_env())
    args = parser.parse_args()

    token = os.environ.get("SUPABASE_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("SUPABASE_ACCESS_TOKEN is required.")
    if not args.project_ref:
        raise RuntimeError("Pass --project-ref or set SUPABASE_PROJECT_REF.")

    schema = validate_identifier(args.schema)
    with open(args.report, encoding="utf-8") as file:
        report = json.load(file)

    ensure_schema(args.project_ref, token, schema)
    run_id = insert_report(args.project_ref, token, schema, report)
    print(f"Synced {args.report} to Supabase run_id {run_id}")


if __name__ == "__main__":
    main()

