"""Prompt construction for scheme simplification and translation.

Pure module: turns a verified scheme record into provider messages. Only
public scheme text is included — never name, mobile, address, income, or any
other user profile data (AGENTS.md 9: free-tier data-use caveat).

The system prompt enforces:
- no facts that are not in the record;
- simple everyday words, roughly a grade 6-8 reading level;
- output as strict JSON with exactly the four required keys.
"""

from __future__ import annotations

import json
from typing import Any

from app.models.enums import Language

# Native names of the six supported languages, so the model knows exactly
# which script and language to write in.
LANGUAGE_NAMES: dict[str, str] = {
    Language.ENGLISH.value: "English",
    Language.TAMIL.value: "Tamil",
    Language.HINDI.value: "Hindi",
    Language.TELUGU.value: "Telugu",
    Language.KANNADA.value: "Kannada",
    Language.MALAYALAM.value: "Malayalam",
}

SYSTEM_INSTRUCTIONS = (
    "You write short, trustworthy explanations of Indian government welfare "
    "schemes for citizens who may have limited literacy.\n"
    "Rules you must never break:\n"
    "1. Use ONLY the facts in the scheme record. Add no new schemes, amounts, "
    "deadlines, documents, or conditions that are not in the record.\n"
    "2. Never mention a real person or organisation beyond the record.\n"
    "3. Use simple everyday words, short sentences, and no jargon. Read like "
    "grade 6-8 school text.\n"
    "4. Write your ENTIRE answer in {language} (the language a citizen "
    "selected). Do not mix another language except unavoidable proper nouns.\n"
    "5. Keep numbers exactly as they appear (amounts, ages, dates).\n"
    "6. Answer with strict JSON only - no markdown, no extra text - shaped "
    "exactly like:\n"
    '{"simple_title": str, "simple_description": str, '
    '"simple_benefits": [str], "simple_steps": [str]}\n'
    "simple_description: 2-4 sentences answering 'What is this scheme?'.\n"
    "simple_benefits: 1-5 short bullet phrases about what a person can get.\n"
    "simple_steps: 3-6 short 'what to do next' steps, based only on the "
    "application steps in the record."
)


def scheme_payload(scheme: dict[str, Any]) -> dict[str, Any]:
    """Public-facing subset of the record passed to the model."""
    return {
        "name": scheme.get("name"),
        "department": scheme.get("department"),
        "level": scheme.get("level"),
        "state": scheme.get("state"),
        "category": scheme.get("category"),
        "benefit_summary": scheme.get("benefit_summary"),
        "benefit_amount": scheme.get("benefit_amount"),
        "benefit_type": scheme.get("benefit_type"),
        "eligibility_summary": scheme.get("eligibility_summary"),
        "required_documents": scheme.get("required_documents"),
        "application_steps": scheme.get("application_steps"),
        "apply_url": scheme.get("apply_url"),
        "deadline": scheme.get("deadline"),
    }


def build_messages(
    request_scheme: dict[str, Any], language: str
) -> list[dict[str, str]]:
    """Two-role chat messages: system rulebook, user payload."""
    language_name = LANGUAGE_NAMES.get(language, LANGUAGE_NAMES["en"])
    system = SYSTEM_INSTRUCTIONS.replace("{language}", language_name)
    user = json.dumps(scheme_payload(request_scheme), ensure_ascii=False)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Scheme record: {user}"},
    ]


def parse_output(raw: str) -> dict[str, Any]:
    """Parse and validate the model's JSON answer, raising ``ValueError``."""
    text = raw.strip()
    if text.startswith("```"):
        # Tolerate a fenced JSON block even though we asked for raw JSON.
        fence = text.split("\n", 1)
        text = fence[1].rsplit("```", 1)[0].strip() if len(fence) > 1 else ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Response is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("Response JSON must be an object")
    for key in ("simple_title", "simple_description", "simple_benefits", "simple_steps"):
        if key not in payload:
            raise ValueError(f"Response JSON is missing '{key}'")
    if not isinstance(payload["simple_title"], str) or not payload["simple_title"].strip():
        raise ValueError("simple_title must be a non-empty string")
    if (
        not isinstance(payload["simple_description"], str)
        or not payload["simple_description"].strip()
    ):
        raise ValueError("simple_description must be a non-empty string")
    if not isinstance(payload["simple_benefits"], list) or not all(
        isinstance(item, str) and item.strip() for item in payload["simple_benefits"]
    ):
        raise ValueError("simple_benefits must be a list of non-empty strings")
    if not isinstance(payload["simple_steps"], list) or not all(
        isinstance(item, str) and item.strip() for item in payload["simple_steps"]
    ):
        raise ValueError("simple_steps must be a list of non-empty strings")
    return payload
