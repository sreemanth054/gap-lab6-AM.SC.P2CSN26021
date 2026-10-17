import json
import re
import sys

from pydantic import BaseModel, Field, ValidationError, model_validator
from stub_client import StubError, StubRateLimitError 
from client import get_client, get_model
from observability import Timer, estimate_cost, estimate_tokens, log_call

TEMPERATURE = 0.7
MAX_TOKENS = 4096

class Question(BaseModel):
    question: str = Field(min_length=5, max_length=500)
    options: list[str] = Field(min_length=4, max_length=4)
    answer_index: int = Field(ge=0, le=3)

    @model_validator(mode="after")
    def validate_answer(self):
        if self.answer_index >= len(self.options):
            raise ValueError("answer_index must point to an existing option")

        if len(set(option.strip() for option in self.options)) != len(self.options):
            raise ValueError("options must be unique")

        return self


class QuestionPaper(BaseModel):
    questions: list[Question] = Field(min_length=5, max_length=5)


def extract_json(text: str):
    """Extract the first valid JSON value from model output."""
    text = text.strip()

    # Remove markdown code fences if they are present.
    text = re.sub(r"^\s*```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)

    # Try to decode JSON starting from each possible object/array.
    decoder = json.JSONDecoder()

    for index, char in enumerate(text):
        if char not in "{[":
            continue

        try:
            value, _ = decoder.raw_decode(text[index:])
            return value
        except json.JSONDecodeError:
            continue

    raise json.JSONDecodeError("No valid JSON found", text, 0)


def looks_like_refusal(text: str) -> bool:
    """Detect common refusal-style replies before JSON parsing."""
    refusal_patterns = [
        r"\bi can't\b",
        r"\bi cannot\b",
        r"\bi’m unable\b",
        r"\bi'm unable\b",
        r"\bi am unable\b",
        r"\bi won't\b",
        r"\bi will not\b",
        r"\bcan't help with\b",
        r"\bcannot help with\b",
        r"\bnot able to\b",
        r"\bunable to comply\b",
    ]

    lower_text = text.lower()

    return any(re.search(pattern, lower_text) for pattern in refusal_patterns)


def build_prompt(topic: str) -> str:
    return f"""
Generate exactly five multiple-choice questions about: {topic}

Return ONLY a JSON object in this exact structure:

{{
  "questions": [
    {{
      "question": "question text",
      "options": [
        "option 1",
        "option 2",
        "option 3",
        "option 4"
      ],
      "answer_index": 0
    }}
  ]
}}

Rules:
- There must be exactly five questions.
- Each question must have exactly four options.
- answer_index must be 0, 1, 2, or 3.
- answer_index identifies the correct option in the options list.
- Do not use Markdown code fences.
- Do not add explanations or text before or after the JSON.
"""


def call_model(client, model: str, prompt: str) -> dict:
    """Make ONE model call and time it. It does not log; it reports what happened."""
    error = None
    response = None

    with Timer() as timer:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
            )
        except Exception as exc:
            error = exc

    if error is not None:
        # The call never completed, so tokens and cost are unknown: None, not 0.
        return {
            "error": error, "text": "", "model": model,
            "prompt_tokens": None, "completion_tokens": None,
            "estimated": False, "latency_ms": timer.ms,
        }

    text = response.choices[0].message.content or ""
    usage = getattr(response, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", None)
    completion_tokens = getattr(usage, "completion_tokens", None)
    estimated = False

    # Usage missing or zeroed: fall back to our own estimate and say so.
    if (prompt_tokens is None or completion_tokens is None
            or (prompt_tokens == 0 and completion_tokens == 0)):
        prompt_tokens = estimate_tokens(prompt)
        completion_tokens = estimate_tokens(text)
        estimated = True

    return {
        "error": None, "text": text,
        "model": getattr(response, "model", None) or model,
        "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
        "estimated": estimated, "latency_ms": timer.ms,
    }


def classify(text: str):
    """Turn a reply into (status, paper). Status is ok, invalid_output or refused."""
    if not text.strip():
        return "invalid_output", None

    try:
        data = extract_json(text)
        return "ok", QuestionPaper.model_validate(data)
    except (json.JSONDecodeError, ValidationError):
        # Only call it a refusal if the reply is not usable JSON.
        if looks_like_refusal(text):
            return "refused", None
        return "invalid_output", None


def record(result: dict, status: str, **extra):
    """Write exactly one log line for one model call."""
    cost = estimate_cost(result["prompt_tokens"], result["completion_tokens"])
    log_call(
        status, result["model"],
        result["prompt_tokens"], result["completion_tokens"],
        result["latency_ms"], cost,
        tokens_estimated=result["estimated"], **extra,
    )


def generate(topic: str):
    client = get_client()
    model = get_model()
    prompt = build_prompt(topic)

    for attempt in range(1, 4):
        result = call_model(client, model, prompt)

        if result["error"] is None:
            status, paper = classify(result["text"])
            record(result, status)

            if status == "refused":
                return "refused", None
            if status == "invalid_output" and attempt == 1:
                prompt = (
                    build_prompt(topic) +
                    "\n\nYour previous response was invalid. "
                    "Return ONLY valid JSON matching the required schema."
                )
                continue
            return status, paper

        record(
            result,
            "error",
            error_type=type(result["error"]).__name__,
        )

        if attempt == 3:
            return "error", None

        delay = min(2 ** attempt, 8)

        retry_after = getattr(result["error"], "retry_after", None)
        if retry_after is not None:
            delay = max(delay, retry_after)

        import random
        import time

        delay += random.uniform(0, 1)
        delay = min(delay, 8)

        time.sleep(delay)

    return "error", None


def main():
    # Input gate: reject invalid topics before making a model call.
    if len(sys.argv) != 2:
        print("error")
        sys.exit(2)

    topic = sys.argv[1]

    if not topic.strip() or len(topic) < 3 or len(topic) > 200:
        print("error")
        sys.exit(2)

    try:
        status, paper = generate(topic)
    except Exception:
        print("error")
        sys.exit(1)

    if status == "ok":
        print(json.dumps(paper.model_dump(), indent=2))
        print("ok")
        sys.exit(0)

    print(status)
    sys.exit(1)


if __name__ == "__main__":
    main()