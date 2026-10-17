"""security.py — the security event log.

Supplied. You may edit it, add fields and add helpers. You may not rename or
remove the five keys, and you may not invent new event names: the marking
script looks for these exact strings.

A guardrail that never writes a line here is, as far as marking is concerned,
a guardrail that never ran. "Present in the file" is not the same as "invoked".

Usage:

    import security

    security.log_event(
        security.GUARDRAIL_INPUT,
        where="guards.py:strip_instructions",
        detail="removed 2 instruction lines from corpus/06_exam_security_handbook.pdf",
    )

Every line lands in security_log.jsonl in the repository root. That file is in
.gitignore and is never committed. You commit samples/security_log_sample.jsonl
instead.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path("security_log.jsonl")

# -- the event vocabulary. These strings are fixed. ------------------------

#: An input guardrail changed or rejected text on its way to the model.
GUARDRAIL_INPUT = "guardrail_input"

#: An output guardrail rejected or scrubbed something on its way back.
GUARDRAIL_OUTPUT = "guardrail_output"

#: An instruction found inside a document was identified and not acted on.
INSTRUCTION_IGNORED = "instruction_ignored"

#: A tool call was refused because its arguments did not validate.
TOOL_ARG_REJECTED = "tool_arg_rejected"

#: A tool returned something that failed validation and was not passed on.
TOOL_RESULT_REJECTED = "tool_result_rejected"

#: A generated question was not stored because it already existed.
DUPLICATE_BLOCKED = "duplicate_blocked"

#: The tool loop hit its documented cap and stopped.
LOOP_CAP_REACHED = "loop_cap_reached"

EVENTS = (
    GUARDRAIL_INPUT,
    GUARDRAIL_OUTPUT,
    INSTRUCTION_IGNORED,
    TOOL_ARG_REJECTED,
    TOOL_RESULT_REJECTED,
    DUPLICATE_BLOCKED,
    LOOP_CAP_REACHED,
)

_RUN_ID = os.environ.get("GAP_RUN_ID") or uuid.uuid4().hex[:12]


def run_id() -> str:
    """One id shared by every event in one run of main.py."""
    return _RUN_ID


def log_event(event: str, where: str, detail: str = "") -> dict:
    """Append one security event. Returns the record it wrote.

    event   one of the constants above
    where   file and function, e.g. "guards.py:strip_instructions"
    detail  what actually happened. No secrets, no full prompts, no full replies.
    """
    if event not in EVENTS:
        raise ValueError(f"Unknown security event {event!r}. Known events: {', '.join(EVENTS)}")

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": _RUN_ID,
        "event": event,
        "where": where,
        "detail": str(detail)[:400],
    }
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    return record


def read_events(path: Path | str = LOG_PATH) -> list[dict]:
    """Every well-formed event in the log. Bad lines are skipped."""
    path = Path(path)
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events

import re

_INSTRUCTION_PATTERNS = [
    ("override_previous", r"\b(ignore|disregard|forget)\b.{0,40}\b(previous|prior|above|earlier|all)\b.{0,40}\b(instructions?|rules?|prompts?|topic list)\b"),
    ("new_instructions", r"\bnew\s+instructions?\b"),
    ("addressed_to_model", r"\binstructions?\s+(for|to)\s+the\s+(assistant|model|ai|llm)\b"),
    ("system_note", r"\bsystem\s+(note|message|prompt|override)\s*:"),
    ("append_code", r"\b(append|add|attach|include|insert)\b.{0,40}\b(verification|tracking|internal)\b.{0,20}\bcode\b"),
    ("takes_precedence", r"\btakes?\s+precedence\s+over\b"),
    ("policy_changed", r"\bpolic(y|ies)\b.{0,40}\b(has|have)\s+changed\b"),
    ("skip_review", r"\b(review|approval|check)\s+step\b.{0,60}\b(skipped|bypassed|omitted)\b"),
    ("record_source_as", r"\brecord\s+the\s+source\b.{0,80}\bas\b"),
]

_COMPILED = [
    (name, re.compile(pattern, re.IGNORECASE | re.DOTALL))
    for name, pattern in _INSTRUCTION_PATTERNS
]

_SENTENCE = re.compile(r"[^.!?]+(?:[.!?]+|$)", re.DOTALL)


def sanitise_document(doc: dict) -> dict:
    """Remove sentences that read like instructions aimed at the model.

    Returns a copy of the document with the cleaned text and the new char count.
    The four document keys are kept. Logs guardrail_input once per document that
    was changed, and instruction_ignored once per removed sentence.
    """
    text = doc["text"]
    kept = []
    removed = []

    for match in _SENTENCE.finditer(text):
        sentence = match.group(0)
        rule = next((name for name, rx in _COMPILED if rx.search(sentence)), None)

        if rule is None:
            kept.append(sentence)
            continue

        start = match.start() + (len(sentence) - len(sentence.lstrip()))
        line = text.count("\n", 0, start) + 1
        snippet = " ".join(sentence.split())[:60]
        removed.append((line, rule, snippet))

    if not removed:
        return doc

    log_event(
        GUARDRAIL_INPUT,
        where="security.py:sanitise_document",
        detail=f"removed {len(removed)} instruction-like sentence(s) from {doc['source']}",
    )
    for line, rule, snippet in removed:
        log_event(
            INSTRUCTION_IGNORED,
            where="security.py:sanitise_document",
            detail=f"{doc['source']} line {line} rule={rule}: {snippet}",
        )

    cleaned = "".join(kept)
    return {**doc, "text": cleaned, "chars": len(cleaned)}

_CLAIM_PATTERNS = [
    ("approval_claim", r"\bapproved\s+by\b"),
    ("verification_code", r"\bverification\s+code\b"),
    ("marker_token", r"\b[A-Z]{3,}-[0-9A-F]{4}\b"),
]

_CLAIMS = [(name, re.compile(rx, re.IGNORECASE if name != "marker_token" else 0))
           for name, rx in _CLAIM_PATTERNS]



def check_paper(paper, allowed_sources: set) -> bool:
    """Content check on a reply that already passed the schema.

    Returns True if the paper is clean. Logs one guardrail_output event per
    offending question, naming the question number and the rules it broke.
    """
    problems = []

    for number, q in enumerate(paper.questions, start=1):
        rules = []

        if q.source not in allowed_sources:
            rules.append("source_not_in_ingest_list")

        texts = [q.question, *q.options]

        for name, rx in _COMPILED + _CLAIMS:
            if any(rx.search(text) for text in texts):
                rules.append(name)

        if rules:
            problems.append((number, rules))

    for number, rules in problems:
        log_event(
            GUARDRAIL_OUTPUT,
            where="security.py:check_paper",
            detail=f"question {number} rejected: {', '.join(rules)}",
        )

    # Record that the output guardrail ran, even when no problems were found.
    log_event(
        GUARDRAIL_OUTPUT,
        where="security.py:check_paper",
        detail=(
            "output guardrail passed"
            if not problems
            else "output guardrail rejected content"
        ),
    )

    return not problems
