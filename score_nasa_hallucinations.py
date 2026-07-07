from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from typing import Any


def field(question: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}: (.*)$", question, re.MULTILINE)
    return match.group(1).strip() if match else ""


def expected_metadata(item: dict[str, Any]) -> dict[str, str]:
    question = item["question"]
    return {
        "article_id": field(question, "NASA article id"),
        "title": field(question, "Title"),
        "authors": field(question, "Authors"),
        "nasa_center": field(question, "NASA center"),
        "sti_type": field(question, "STI type"),
        "publication": field(question, "Publication"),
        "publication_date": field(question, "Publication date"),
        "distribution_date": field(question, "Distribution date"),
        "doi": field(question, "DOI"),
        "report_numbers": field(question, "Report numbers"),
        "ntrs_url": field(question, "NTRS URL"),
        "source_topics": field(question, "Source topics"),
    }


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_type(text: str) -> str:
    text = text.lower().replace("-", "_").replace(" ", "_")
    synonyms = {
        "reprint": "reprint",
        "conference_paper": "conference_paper",
        "conference_proceedings": "conference_proceedings",
        "contractor_report": "contractor_report",
        "technical_memorandum": "technical_memorandum",
        "book": "book",
        "preprint": "preprint",
        "other": "other",
        "journal_article": "journal_article",
        "research_paper": "research_paper",
    }
    for key, value in synonyms.items():
        if key in text:
            return value
    return text


def extract_stated_document_type(answer: str) -> str | None:
    patterns = [
        r"document type(?: is|:)?\s+([A-Za-z_ -]+?)(?:[.;,\n]|$)",
        r"STI type(?: is| as|:)?\s+([A-Za-z_ -]+?)(?:[.;,\n]|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, answer, flags=re.IGNORECASE)
        if match:
            return clean(match.group(1))
    return None


def score_answer(answer: str, meta: dict[str, str]) -> tuple[int, list[str]]:
    notes: list[str] = []
    major = False
    minor = False
    answer_clean = clean(answer)
    answer_lower = answer_clean.lower()

    expected_url = meta["ntrs_url"]
    urls = re.findall(r"https?://ntrs\.nasa\.gov/[^\s),.;]+", answer_clean)
    wrong_urls = [url for url in urls if url != expected_url]
    if wrong_urls:
        major = True
        notes.append(f"Wrong NTRS URL stated: {', '.join(wrong_urls[:2])}.")

    expected_id = meta["article_id"]
    ids = set(re.findall(r"\b(?:nasa-)?(19\d{9})\b", answer_clean, flags=re.IGNORECASE))
    ids.discard(expected_id)
    if ids:
        major = True
        notes.append(f"Wrong NASA article id/reference detected: {', '.join(sorted(ids)[:3])}.")

    expected_doi = meta["doi"]
    doi_matches = re.findall(r"\b10\.\d{4,9}/[^\s),.;]+", answer_clean)
    if expected_doi == "Not listed" and doi_matches:
        major = True
        notes.append(f"Invented DOI: {', '.join(doi_matches[:2])}.")
    elif expected_doi != "Not listed":
        wrong_doi = [doi for doi in doi_matches if doi != expected_doi]
        if wrong_doi:
            major = True
            notes.append(f"Wrong DOI stated: {', '.join(wrong_doi[:2])}.")
        if re.search(r"\b(no|not|none)\b.{0,25}\bdoi\b|\bdoi\b.{0,25}\b(no|not|none)\b", answer_lower):
            major = True
            notes.append("Answer says no DOI is listed even though the source has a DOI.")

    expected_reports = meta["report_numbers"]
    if expected_reports != "Not listed" and re.search(
        r"\b(no|not|none)\b.{0,35}\breport numbers?\b|\breport numbers?\b.{0,35}\b(no|not|none)\b",
        answer_lower,
    ):
        major = True
        notes.append("Answer says report numbers are not listed even though the source lists report numbers.")

    stated_type = extract_stated_document_type(answer_clean)
    if stated_type:
        expected_type = normalize_type(meta["sti_type"])
        observed_type = normalize_type(stated_type)
        if observed_type and expected_type and observed_type != expected_type:
            # "journal article" is a common but unsupported replacement for REPRINT.
            if observed_type in {"journal_article", "research_paper"} or expected_type != "other":
                major = True
                notes.append(
                    f"Document type mismatch: stated {stated_type!r}, expected {meta['sti_type']!r}."
                )
            else:
                minor = True
                notes.append(
                    f"Document type phrasing is unsupported: stated {stated_type!r}, expected {meta['sti_type']!r}."
                )

    unsupported_patterns = [
        (r"\bconducted at\b.*\b(?:legacy cdms|headquarters|cdms|hq)\b", "Treats NASA center metadata as where the research was conducted."),
        (r"\b(?:from|at|by)\s+(?:nasa'?s\s+)?legacy cdms\b", "Treats Legacy CDMS as author affiliation, publisher, or source rather than center metadata."),
        (r"\bpublished (?:at|by|in)\s+(?:nasa'?s\s+)?legacy cdms\b", "Treats Legacy CDMS as a publication venue or publisher."),
        (r"\blast updated\b|\bupdated (?:on|version)\b", "Treats distribution date as an update date."),
        (r"\breprinted (?:on|from|for)\b", "Blends STI type REPRINT with distribution/publication metadata."),
        (r"\bfull text can be accessed\b", "Claims full text access where only an NTRS citation URL is provided."),
        (r"\bcosmic data mining\b", "Invents an expansion of CDMS not present in the source metadata."),
        (r"\bjournal of pluto\b", "Invents a publication name."),
    ]
    for pattern, note in unsupported_patterns:
        if re.search(pattern, answer_lower, flags=re.IGNORECASE):
            if "journal of pluto" in pattern:
                major = True
            else:
                minor = True
            notes.append(note)

    if meta["authors"] == "Not listed" and re.search(r"\bby [A-Z][A-Za-z]+", answer_clean):
        minor = True
        notes.append("Source lists authors as not listed, but answer appears to imply an author.")

    if major:
        return 2, notes
    if minor:
        return 1, notes
    return 0, ["No obvious hallucination detected by metadata checks."]


def mode_answer(item: dict[str, Any], mode_name: str) -> str:
    for mode in item["modes"]:
        if mode["mode"] == mode_name:
            return str(mode.get("answer_text") or "")
    raise KeyError(f"Missing mode {mode_name!r} for {item.get('id')}")


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
    total_sum = sum(sums.values())
    for mode in sorted(by_mode):
        score_counts = {str(score): by_mode[mode][str(score)] for score in range(3)}
        count = counts[mode]
        any_hallucination = score_counts["1"] + score_counts["2"]
        summary[mode] = {
            "mode_scores_count": count,
            "score_counts": score_counts,
            "any_hallucination_rate": round(any_hallucination / count, 4),
            "major_hallucination_rate": round(score_counts["2"] / count, 4),
            "average_hallucination_score": round(sums[mode] / count, 4),
        }
    summary["average_hallucination_score"] = round(total_sum / sum(all_scores.values()), 4)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Score NASA metadata hallucinations deterministically.")
    parser.add_argument("input", help="Evaluation JSON path.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as file:
        report = json.load(file)

    items = report["results"]
    if args.limit:
        items = items[: args.limit]

    results = []
    for item in items:
        meta = expected_metadata(item)
        mode_scores = []
        for mode_name in ("direct", "factored_cove"):
            score, notes = score_answer(mode_answer(item, mode_name), meta)
            mode_scores.append(
                {
                    "mode": mode_name,
                    "manual_hallucination_score": score,
                    "notes": " ".join(notes),
                }
            )
        results.append(
            {
                "id": item["id"],
                "category": item["category"],
                "reference": meta,
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

    scoring_report = {
        "source_file": args.input,
        "source_model": report.get("model"),
        "scoring_scale": {
            "hallucination": "0=none obvious, 1=minor/uncertain, 2=major invented claims"
        },
        "scoring_method": (
            "Deterministic NASA metadata checks. The scorer compares direct and factored_cove "
            "answers against source metadata in each prompt, flags concrete contradictions "
            "such as wrong NTRS URLs, DOI/report-number conflicts, wrong document type claims, "
            "and recurring unsupported metadata-role claims such as treating Legacy CDMS as an "
            "author affiliation, publication venue, or research location. Omissions are not "
            "penalized."
        ),
        "results": results,
        "summary": summarize(results),
    }
    with open(args.output, "w", encoding="utf-8") as file:
        json.dump(scoring_report, file, indent=2)
        file.write("\n")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
