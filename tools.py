"""tools.py — the two read-only tools.

Neither tool writes. Neither tool gets a shell. Both validate their arguments
before doing anything, and both validate their results before anything is
handed back to the model.

Every capability an agent has is a permission your code granted. There are no
others. The model can ask for anything. What it can reach is this file.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

import security

# A tool may read inside DATA_DIR and nowhere else. Resolved once, at import time.
DATA_DIR = Path(__file__).parent.joinpath("data").resolve()

#: The documented cap on tool round trips in one run (also in SPEC.md).
MAX_TOOL_STEPS = 5


# --------------------------------------------------------------------------
# Argument models. The tool schemas are generated from these.
# --------------------------------------------------------------------------

class TopicLookupArgs(BaseModel):
    """Arguments for topic_lookup. There is no filename here, on purpose."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=2, max_length=60,
                       description="A word or phrase to match against the client's "
                                   "approved topic names. Case-insensitive.")
    limit: int = Field(10, ge=1, le=50,
                       description="How many matching topics to return at most.")


class QuestionLookupArgs(BaseModel):
    """Arguments for question_lookup."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=200,
                       description="Text to match against questions already generated.")
    limit: int = Field(5, ge=1, le=50,
                       description="How many matches to return at most.")


# --------------------------------------------------------------------------
# Result models. A tool result is untrusted too.
# --------------------------------------------------------------------------

class TopicRecord(BaseModel):
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1, max_length=200)


class QuestionRecord(BaseModel):
    id: str = Field(..., min_length=1)
    topic: str = Field(..., min_length=1, max_length=200)
    text: str = Field(..., min_length=1, max_length=2000)
    source: str = Field(..., min_length=1, max_length=300)


# --------------------------------------------------------------------------
# The allow-list
# --------------------------------------------------------------------------

class ToolRefused(Exception):
    """Raised when a tool declines to act.

    It carries nothing the model can use: no path, no traceback, no directory
    listing.
    """


#: The only two files a tool may ever open.
ALLOWED_FILES = ("topics.json", "generated_questions.json")


def _problems(exc: ValidationError) -> str:
    """Field names and error types only. Never echoes the input back."""
    return ", ".join(
        f"{'.'.join(str(part) for part in err['loc']) or 'body'}:{err['type']}"
        for err in exc.errors()
    )


def _row_id(row) -> str:
    if isinstance(row, dict):
        return str(row.get("id", "?"))[:40]
    return "?"


def load_data_file(name: str) -> str:
    """Open one of the two allow-listed files inside data/, and nothing else.

    This is the ONLY place in the tools where a path is built. The name comes
    from our own code, never from the model. It is still written defensively.
    """
    if not isinstance(name, str) or name not in ALLOWED_FILES:
        security.log_event(
            security.TOOL_ARG_REJECTED,
            where="tools.py:load_data_file",
            detail=f"file name not on the allow-list: {str(name)[:60]!r}",
        )
        raise ToolRefused("That file is not available.")

    # Resolve BEFORE comparing: a symbolic link can point anywhere, and
    # is_relative_to compares path components, not characters.
    path = DATA_DIR.joinpath(name).resolve()
    if not path.is_relative_to(DATA_DIR) or not path.is_file():
        security.log_event(
            security.TOOL_ARG_REJECTED,
            where="tools.py:load_data_file",
            detail=f"resolved path left data/ or is not a file: {name}",
        )
        raise ToolRefused("That file is not available.")

    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        security.log_event(
            security.TOOL_RESULT_REJECTED,
            where="tools.py:load_data_file",
            detail=f"could not read {name}",
        )
        raise ToolRefused("That file is not available.")


def _read_rows(filename: str, key: str) -> list:
    """Read an allow-listed file and return the list stored under `key`."""
    raw = load_data_file(filename)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = None

    rows = data.get(key) if isinstance(data, dict) else None
    if not isinstance(rows, list):
        security.log_event(
            security.TOOL_RESULT_REJECTED,
            where="tools.py:_read_rows",
            detail=f"{filename} is not valid JSON or has no '{key}' list",
        )
        raise ToolRefused("That data is not available.")
    return rows


# --------------------------------------------------------------------------
# The tools
# --------------------------------------------------------------------------

def topic_lookup(**kwargs) -> dict:
    """Search the topic list the client keeps outside the application.

    Returns {"matches": [ ... ]} where each match is a validated TopicRecord.
    A traversal string such as "../.env" is just a topic nobody has: it matches
    nothing and the tool returns an empty list.
    """
    try:
        args = TopicLookupArgs(**kwargs)
    except ValidationError as exc:
        security.log_event(
            security.TOOL_ARG_REJECTED,
            where="tools.py:topic_lookup",
            detail=f"arguments did not validate: {_problems(exc)}",
        )
        raise ToolRefused("The arguments did not validate.")

    words = args.query.lower().split()
    if not words:
        return {"matches": []}

    rows = _read_rows("topics.json", "topics")

    matches = []
    for row in rows:
        try:
            record = TopicRecord.model_validate(row)
        except ValidationError as exc:
            security.log_event(
                security.TOOL_RESULT_REJECTED,
                where="tools.py:topic_lookup",
                detail=f"topic row {_row_id(row)} rejected: {_problems(exc)}",
            )
            continue
        # Match against the topic NAME only. Never against a filename.
        if all(word in record.name.lower() for word in words):
            matches.append(record.model_dump())

    return {"matches": matches[: args.limit]}


def question_lookup(**kwargs) -> dict:
    """Search the questions this application has already generated.

    Returns {"matches": [ ... ]} where each match is a validated QuestionRecord.
    A row that does not validate is logged by id and never passed on.
    """
    try:
        args = QuestionLookupArgs(**kwargs)
    except ValidationError as exc:
        security.log_event(
            security.TOOL_ARG_REJECTED,
            where="tools.py:question_lookup",
            detail=f"arguments did not validate: {_problems(exc)}",
        )
        raise ToolRefused("The arguments did not validate.")

    words = args.query.lower().split()

    rows = _read_rows("generated_questions.json", "questions")

    matches = []
    # Every row is validated, matched or not, so a bad row is always reported.
    for row in rows:
        try:
            record = QuestionRecord.model_validate(row)
        except ValidationError as exc:
            security.log_event(
                security.TOOL_RESULT_REJECTED,
                where="tools.py:question_lookup",
                detail=f"question row {_row_id(row)} rejected: {_problems(exc)}",
            )
            continue
        haystack = f"{record.text} {record.topic}".lower()
        if words and all(word in haystack for word in words):
            matches.append(record.model_dump())

    return {"matches": matches[: args.limit]}


# --------------------------------------------------------------------------
# The schemas the model sees
# --------------------------------------------------------------------------

TOOL_FUNCTIONS = {
    "topic_lookup": topic_lookup,
    "question_lookup": question_lookup,
}

TOOL_ARGS = {
    "topic_lookup": TopicLookupArgs,
    "question_lookup": QuestionLookupArgs,
}

TOOL_DESCRIPTIONS = {
    "topic_lookup": (
        "Search the client's approved topic list by topic name. Use it to check "
        "which topics the client allows before writing questions. Pass a word or "
        "phrase from a topic name, for example 'bloom' or 'distractor'. Returns "
        "up to `limit` matches, each with an id and a name. It searches topic "
        "names only. It does not read files and does not take a path."
    ),
    "question_lookup": (
        "Search the questions that have already been generated and stored. Use "
        "it before writing a question, to check whether a similar one already "
        "exists, so that you do not repeat it. Pass a word or phrase from the "
        "question or its topic. Returns up to `limit` matches, each with an id, "
        "topic, text and source. It does not read files and does not take a path."
    ),
}


def get_tool_schemas() -> list[dict]:
    """The tool schemas, in OpenAI function-calling form.

    The `parameters` value comes from the Pydantic model, so it cannot drift
    from the model the first time a field changes.
    """
    schemas = []
    for name, args_model in TOOL_ARGS.items():
        schemas.append({
            "type": "function",
            "function": {
                "name": name,
                "description": TOOL_DESCRIPTIONS[name],
                "parameters": args_model.model_json_schema(),
            },
        })
    return schemas


def run_tool(name: str, arguments: dict) -> dict:
    """Dispatch one tool call by name.

    Returns a dict that is safe to put in a tool message. On refusal it returns
    a dict describing the refusal rather than raising, so the loop can tell the
    model it was refused and carry on. Never returns a traceback or a path.
    """
    if name not in TOOL_FUNCTIONS:
        security.log_event(
            security.TOOL_ARG_REJECTED,
            where="tools.py:run_tool",
            detail=f"unknown tool name: {str(name)[:60]!r}",
        )
        return {"error": "That tool does not exist."}

    if not isinstance(arguments, dict):
        security.log_event(
            security.TOOL_ARG_REJECTED,
            where="tools.py:run_tool",
            detail=f"arguments for {name} were not an object",
        )
        return {"error": "The arguments did not validate."}

    try:
        return TOOL_FUNCTIONS[name](**arguments)
    except ToolRefused as exc:
        return {"error": str(exc)}
    except Exception as exc:
        security.log_event(
            security.TOOL_RESULT_REJECTED,
            where="tools.py:run_tool",
            detail=f"{name} failed with {type(exc).__name__}",
        )
        return {"error": "The tool could not complete."}