from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Optional

from openai import OpenAI, OpenAIError

from .config import DEFAULT_LLM_MODEL, get_db_path
from .dictionary import ensure_cache_schema
from .models import GrammarPoint, SentenceExplanation


openai_client: Optional[OpenAI] = None


def explain_sentence(sentence: str) -> SentenceExplanation:
    model = os.environ.get("JP_LLM_MODEL", DEFAULT_LLM_MODEL)
    cached = get_cached_explanation(sentence, model)
    if cached is not None:
        return cached

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return SentenceExplanation(
            meaning="",
            yasashiku="",
            grammar_points=[],
            nuance="",
            raw=(
                "OPENAI_API_KEY is not configured.\n\n"
                "Create a .env file with:\n"
                "OPENAI_API_KEY=your_api_key_here\n"
                f"JP_LLM_MODEL={DEFAULT_LLM_MODEL}"
            ),
        )

    prompt = build_explanation_prompt(sentence)

    try:
        response = get_openai_client().responses.create(
            model=model,
            input=prompt,
            temperature=0.4,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "japanese_sentence_explanation",
                    "description": "N2-friendly explanation of a Japanese sentence.",
                    "strict": True,
                    "schema": explanation_schema(),
                },
                "verbosity": "medium",
            },
        )
    except OpenAIError as error:
        return SentenceExplanation(
            meaning="",
            yasashiku="",
            grammar_points=[],
            nuance="",
            raw=f"Could not generate explanation with {model}:\n{error}",
        )

    output_text = getattr(response, "output_text", "")
    explanation = parse_explanation(output_text.strip())
    if explanation.raw is None:
        save_cached_explanation(sentence, model, explanation)
    return explanation


def get_cached_explanation(sentence: str, model: str) -> Optional[SentenceExplanation]:
    if not get_db_path().exists():
        return None

    ensure_cache_schema()
    connection = sqlite3.connect(get_db_path())
    try:
        row = connection.execute(
            """
            select explanation_json
            from explanation_cache
            where sentence = ? and model = ?
            """,
            (sentence, model),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return None
    return explanation_from_json(row[0])


def save_cached_explanation(sentence: str, model: str, explanation: SentenceExplanation) -> None:
    ensure_cache_schema()
    connection = sqlite3.connect(get_db_path())
    try:
        connection.execute(
            """
            insert or replace into explanation_cache(sentence, model, explanation_json, created_at)
            values (?, ?, ?, ?)
            """,
            (
                sentence,
                model,
                explanation_to_json(explanation),
                time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def explanation_to_json(explanation: SentenceExplanation) -> str:
    return json.dumps(
        {
            "meaning": explanation.meaning,
            "yasashiku": explanation.yasashiku,
            "grammar_points": [
                {"title": point.title, "explanation": point.explanation}
                for point in explanation.grammar_points
            ],
            "nuance": explanation.nuance,
        },
        ensure_ascii=False,
    )


def explanation_from_json(payload: str) -> SentenceExplanation:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return SentenceExplanation("", "", [], "", raw=payload)

    return SentenceExplanation(
        meaning=str(data.get("meaning", "")).strip(),
        yasashiku=str(data.get("yasashiku", "")).strip(),
        grammar_points=[
            GrammarPoint(
                title=str(point.get("title", "")).strip(),
                explanation=str(point.get("explanation", "")).strip(),
            )
            for point in data.get("grammar_points", [])
            if isinstance(point, dict)
        ],
        nuance=str(data.get("nuance", "")).strip(),
    )


def explanation_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "meaning": {
                "type": "string",
                "description": "A natural English translation of the sentence.",
            },
            "yasashiku": {
                "type": "string",
                "description": "Simple Japanese explanation suitable for a JLPT N2 learner.",
            },
            "grammar_points": {
                "type": "array",
                "description": "Important grammar points in the sentence.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string"},
                        "explanation": {"type": "string"},
                    },
                    "required": ["title", "explanation"],
                },
            },
            "nuance": {
                "type": "string",
                "description": "Useful nuance, implication, or naturalness note.",
            },
        },
        "required": ["meaning", "yasashiku", "grammar_points", "nuance"],
    }


def parse_explanation(output_text: str) -> SentenceExplanation:
    if not output_text:
        return SentenceExplanation("", "", [], "", raw="The model returned an empty explanation.")

    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError:
        return SentenceExplanation("", "", [], "", raw=output_text)

    grammar_points = [
        GrammarPoint(
            title=str(item.get("title", "")).strip(),
            explanation=str(item.get("explanation", "")).strip(),
        )
        for item in payload.get("grammar_points", [])
        if isinstance(item, dict)
    ]

    return SentenceExplanation(
        meaning=str(payload.get("meaning", "")).strip(),
        yasashiku=str(payload.get("yasashiku", "")).strip(),
        grammar_points=grammar_points,
        nuance=str(payload.get("nuance", "")).strip(),
    )


def format_explanation(explanation: SentenceExplanation) -> str:
    if explanation.raw:
        return explanation.raw

    lines = [
        "意味:",
        explanation.meaning,
        "",
        "やさしく説明:",
        explanation.yasashiku,
        "",
        "文法ポイント:",
    ]
    for point in explanation.grammar_points:
        lines.append(f"- {point.title}")
        lines.append(f"  {point.explanation}")
    lines.extend(["", "ニュアンス:", explanation.nuance])
    return "\n".join(lines).strip()


def get_openai_client() -> OpenAI:
    global openai_client
    if openai_client is None:
        openai_client = OpenAI()
    return openai_client


def build_explanation_prompt(sentence: str) -> str:
    return f"""
You are helping an intermediate Japanese learner around JLPT N2 level.

Explain this sentence:
{sentence}

Return only the requested structured data.

Keep each field compact and readable in a terminal.
""".strip()
