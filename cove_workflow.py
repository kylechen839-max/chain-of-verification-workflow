from __future__ import annotations

from dataclasses import dataclass
import json
import re
import urllib.error
import urllib.request
from typing import Any, Callable


Message = dict[str, str]
CallLLM = Callable[[list[Message]], str]


@dataclass
class CoVeResult:
    question: str
    draft: str
    verification_questions: list[str]
    verification_answers: list[str]
    final: str


def _as_bullets(items: list[str]) -> str:
    return "\n".join(f"{i + 1}. {item}" for i, item in enumerate(items))


def _parse_questions(text: str, max_questions: int) -> list[str]:
    text = text.strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            parsed = parsed.get("questions", [])
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()][:max_questions]
    except json.JSONDecodeError:
        pass

    questions: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        match = re.match(r"^(?:[-*]|\d+[.)])\s*(.+)$", line)
        if match:
            candidate = match.group(1).strip()
            if candidate.endswith("?"):
                questions.append(candidate)
            else:
                questions.extend(_extract_question_spans(candidate))
        elif line.endswith("?"):
            questions.append(line)
        else:
            questions.extend(_extract_question_spans(line))

    deduped: list[str] = []
    seen = set()
    for question in questions:
        cleaned = question.strip(" \"'`[]")
        cleaned = re.sub(r"^\s*\d+\s*[-.)]\s*", "", cleaned)
        cleaned = re.sub(r"^\s*Q\d+\s*[:.)-]\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip(" \"'`[]")
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            deduped.append(cleaned)

    return deduped[:max_questions]


def _extract_question_spans(text: str) -> list[str]:
    return [
        match.strip(" \"'`[]")
        for match in re.findall(r"[^?.!;\n]{10,}\?", text)
        if match.strip()
    ]


def _strip_thinking(text: str) -> str:
    """Remove reasoning blocks emitted by some local reasoning models."""

    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()


def run_factored_cove(
    question: str,
    call_llm: CallLLM,
    max_questions: int = 8,
) -> CoVeResult:
    """Run factored Chain of Verification.

    The verification-answering step intentionally receives only the verification
    question, not the draft answer. That separation is the key CoVe safeguard.
    """

    draft = call_llm(
        [
            {
                "role": "system",
                "content": "You answer clearly and precisely. Do not add caveats unless they matter.",
            },
            {"role": "user", "content": question},
        ]
    ).strip()

    planner_prompt = f"""
Given the user question and draft answer, write up to {max_questions} verification questions
that would fact-check the draft's factual claims.

Rules:
- Prefer open-ended factual questions over yes/no questions.
- Make each question answerable without seeing the draft.
- Focus on atomic claims: dates, names, locations, numbers, causal claims, and entity membership.
- Return JSON only, exactly in this shape: {{"questions": ["...", "..."]}}

User question:
{question}

Draft answer:
{draft}
""".strip()

    question_text = call_llm(
        [
            {
                "role": "system",
                "content": "You are a fact-checking planner. Return valid JSON only.",
            },
            {"role": "user", "content": planner_prompt},
        ]
    )
    verification_questions = _parse_questions(question_text, max_questions=max_questions)

    verification_answers: list[str] = []
    for verification_question in verification_questions:
        answer = call_llm(
            [
                {
                    "role": "system",
                    "content": (
                        "Answer the factual question directly. If the answer is unknown, contested, "
                        "or not inferable from reliable general knowledge, say so."
                    ),
                },
                {"role": "user", "content": verification_question},
            ]
        )
        verification_answers.append(answer.strip())

    rewrite_prompt = f"""
Rewrite the answer to the user question using only the verification answers below as evidence.

Rules:
- Remove or mark claims that are unsupported, uncertain, or contradicted.
- Do not mention this verification process.
- Keep the final answer readable and useful.

User question:
{question}

Verification questions:
{_as_bullets(verification_questions)}

Verification answers:
{_as_bullets(verification_answers)}

Return only the final answer.
""".strip()

    final = call_llm(
        [
            {
                "role": "system",
                "content": "You are a careful editor writing a final verified answer.",
            },
            {"role": "user", "content": rewrite_prompt},
        ]
    ).strip()

    return CoVeResult(
        question=question,
        draft=draft,
        verification_questions=verification_questions,
        verification_answers=verification_answers,
        final=final,
    )


def run_joint_cove(
    question: str,
    call_llm: CallLLM,
    max_questions: int = 8,
) -> dict[str, Any]:
    """Run a one-call CoVe variant.

    This is cheaper and easier to integrate than factored CoVe, but the model can
    still see its own draft while verifying, so it may repeat draft mistakes.
    """

    prompt = f"""
Answer the user question using this process:
1. Draft an initial answer.
2. List up to {max_questions} verification questions that check factual claims in the draft.
3. Answer each verification question.
4. Produce a final answer consistent with the verification answers.
5. If verification is inconclusive, mark the claim as uncertain or remove it.

Return valid JSON only with these keys:
- draft: string
- verification_questions: array of strings
- verification_answers: array of strings
- final: string
- uncertainties: array of strings

User question:
{question}
""".strip()

    raw = call_llm(
        [
            {"role": "system", "content": "You are a careful assistant. Return valid JSON only."},
            {"role": "user", "content": prompt},
        ]
    )

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def make_openai_call_llm(model: str = "gpt-5.5", **request_options: Any) -> CallLLM:
    """Create a call_llm function backed by the OpenAI Responses API.

    Requires:
        pip install openai
        export OPENAI_API_KEY=...
    """

    from openai import OpenAI

    client = OpenAI()

    def call_llm(messages: list[Message]) -> str:
        instructions = "\n\n".join(
            message["content"]
            for message in messages
            if message.get("role") in {"system", "developer"}
        )
        transcript = "\n\n".join(
            f"{message.get('role', 'user').title()}: {message['content']}"
            for message in messages
            if message.get("role") not in {"system", "developer"}
        )

        response = client.responses.create(
            model=model,
            instructions=instructions or None,
            input=transcript,
            **request_options,
        )
        return response.output_text

    return call_llm


def make_ollama_call_llm(
    model: str = "llama3.2:1b",
    host: str = "http://127.0.0.1:11434",
    think: bool | None = False,
    **request_options: Any,
) -> CallLLM:
    """Create a call_llm function backed by a local or remote Ollama server.

    Ollama does not run proprietary ChatGPT models. It can run local/open models,
    such as llama3.2, mistral, qwen, or OpenAI's open-weight gpt-oss models when
    they are available and the machine has enough memory.

    Requires:
        ollama serve
        ollama pull <model>
    """

    endpoint = host.rstrip("/") + "/api/chat"

    def call_llm(messages: list[Message]) -> str:
        options = dict(request_options.get("options", {}))

        def post(chat_messages: list[Message]) -> str:
            payload = {
                "model": model,
                "messages": chat_messages,
                "stream": False,
                "options": {
                    "temperature": 0,
                    **options,
                },
                **{key: value for key, value in request_options.items() if key != "options"},
            }
            if think is not None:
                payload["think"] = think
            data = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                endpoint,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            try:
                with urllib.request.urlopen(request, timeout=300) as response:
                    body = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                detail = error.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"Ollama request failed: {error.code} {detail}") from error
            except urllib.error.URLError as error:
                raise RuntimeError(
                    f"Could not reach Ollama at {host}. Start it with `ollama serve`."
                ) from error

            return _strip_thinking(body.get("message", {}).get("content", ""))

        content = post(messages)
        if content:
            return content

        direct_messages = [
            {
                "role": "system",
                "content": (
                    "Respond with only the final answer in plain text. "
                    "Do not include reasoning, analysis, or <think> tags."
                ),
            },
            *messages,
        ]
        return post(direct_messages)

    return call_llm
