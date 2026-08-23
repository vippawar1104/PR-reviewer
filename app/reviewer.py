from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.config import settings

MODEL = "gemini-2.5-flash"


class Finding(BaseModel):
    file: str
    line: int  # Line number in the NEW version of the file, as shown in the diff.
    severity: Literal["low", "medium", "high"]
    category: Literal["bug", "security", "correctness", "style", "performance"]
    comment: str


class ReviewResult(BaseModel):
    summary: str  # 1-3 sentence overall summary of the PR and the review.
    findings: list[Finding]


SYSTEM_PROMPT = """You are an expert code reviewer performing an automated pull request review.

Only flag genuine issues: bugs, security vulnerabilities, correctness problems, and \
performance issues significant enough to matter in production. Do not comment on \
subjective style preferences or minor nitpicks.

Be conservative: if you are not confident something is actually a problem, do not flag it. \
A missed issue is better than a false positive that erodes trust in this review.

For each finding, cite the exact file and line number in the NEW version of the file \
(as shown in the diff), and explain concretely why it's a problem, not just what it is."""


def build_prompt(pr_title: str, pr_description: str, files: list[dict]) -> str:
    parts = [f"# Pull Request: {pr_title}", "", pr_description or "(no description provided)", ""]

    for f in files:
        parts.append(f"## File: {f['filename']}")
        parts.append("### Diff:")
        parts.append(f.get("patch") or "(no diff patch available)")
        if f.get("content"):
            parts.append("### Full file content (for context):")
            parts.append(f["content"])
        parts.append("")

    return "\n".join(parts)


def parse_review_response(response) -> dict:
    if response.parsed is None:
        raise ValueError(f"Gemini did not return a parseable review: {response.text!r}")
    return response.parsed.model_dump()


def review(pr_title: str, pr_description: str, files: list[dict], client: genai.Client | None = None) -> dict:
    client = client or genai.Client(api_key=settings.gemini_api_key)
    prompt = build_prompt(pr_title, pr_description, files)

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=ReviewResult,
        ),
    )
    return parse_review_response(response)
