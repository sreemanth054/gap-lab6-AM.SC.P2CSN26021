# What it does

The program takes a topic entered by the user and uses AI model to generate five mcqs on the given topic. Each question contains four answer options and one correct answer. The program checks and validates the model's response before accepting it. Only responses that follows the required structure and constraints are accepted.

Every model call is also recorded as one line in run_log.jsonl (tokens, latency, cost), and failed calls are retried under a capped policy.


# Inputs

The topic will be given as a string through the command line. It should be at least 3 characters long and should not exceed 200 characters. Topics containing spaces are allowed, as long as they are entered within quotes. If the topic is missing, empty, contains only spaces, or does not meet the length requirements, the program will reject it without sending anything to the AI model.

The program calls Google's Gemini API (OpenAI-compatible endpoint, free tier) with model gemini-3.8-flash, temperature=0.7 and max_tokens=4096.
Cost is computed from two prices, set in observability.py:
- PRICE_IN_PER_MTOK = 0.75 USD per million input tokens
- PRICE_OUT_PER_MTOK = 3.75 USD per million output tokens
Source: https://ai.google.dev/gemini-api/docs/pricing, checked on 4 October 2026. These are the paid-tier prices of the same model, because the free tier charges nothing. Reported costs are therefore what the same calls would cost on the paid tier, not what was actually charged. Output pricing includes thinking tokens.
If the provider reports no usage or zeroed usage, tokens are estimated with estimate_tokens() and tokens_estimated is set to true on that line.
# Outputs

The program should generate exactly five questions for a valid topic. Each question will have the question itself, four answer options, and an answer_index that shows which option is correct. The generated response will be checked against these requirements before it is accepted.
The last non-empty line printed by the program will always show what happened. It will be one of ok, invalid_output, refused, or error. A valid response will return ok with exit code 0. If the model response is invalid, refused, or an error occurs during the model call, the program will return the corresponding status with exit code 1. If the topic is rejected before contacting the model, the program will exit with code 2.

Each model call appends one JSON object to run_log.jsonl in the repository root (append only, one line per call, so a retry is its own line). All lines from one run share one run_id. The file is in .gitignore and never committed. The nine fields are: timestamp, run_id, model, status, prompt_tokens, completion_tokens, latency_ms, cost_usd, tokens_estimated. Unknown values are null, not 0. The log never contains a key, a full prompt or a full reply.

# Failure cases

If the user does not provide a topic, or if the topic is empty, only contains spaces, or is outside the allowed length, the program will reject it without contacting the AI model, write no line to run_log.jsonl, and exit with code 2.

If the model gives a response that is not valid JSON, the program makes exactly one repair retry. If the retry is also invalid, the program returns invalid_output with exit code 1. This produces 2 log lines.

If the response is valid JSON but does not follow the required format, such as having the wrong number of questions or options, it is handled the same way: exactly one repair retry, then invalid_output with exit code 1 and 2 log lines.

If the model returns nothing, the program treats it as invalid_output, makes exactly one repair retry, and then exits with code 1 if the retry is also empty (2 log lines).

If the model refuses to generate the questions, the program returns refused with exit code 1. A refusal is never retried (1 log line).

If there is an error while communicating with the model or something goes wrong during the model call, the program retries with backoff, up to 3 attempts in total. The delay before each retry is (2 ** attempt) + random.uniform(0, 1) seconds, never above 8 seconds. If the provider sends a Retry-After value longer than that delay, the longer value is used. Every attempt is its own log line, and cost_usd is null on an error line because the call never completed. If all attempts fail, the program returns error with exit code 1 (2 or 3 log lines).

If a call fails once and a later attempt succeeds, the program returns ok with exit code 0. The log shows the error line first, then the ok line.

If the model puts the JSON inside Markdown code blocks or adds some text before the JSON, the program tries to extract the JSON and then validates it. This is not a failure and uses no retry (1 log line).

If the provider reports no usage, or reports zeroed usage, the token counts are estimated with estimate_tokens() and tokens_estimated is true on that line.

# Acceptance checks

A successful generation should produce five valid questions and end with `ok`.

Each stub mode is run on its own. Before each run, delete run_log.jsonl so the line count is for that run only. Every check asserts on shape (last line, exit code, number of log lines, keys present), never on exact model text.

Each stub mode is run with the environment variables set on the command line, after deleting run_log.jsonl so the line count is for that run only. Every check asserts on shape (last line, exit code, number of log lines), never on exact model text.

`LLM_BASE_URL=local://stub LLM_MODEL=stub:ok python main.py "photosynthesis"` → `ok`, exit code 0, 1 log line
`LLM_BASE_URL=local://stub LLM_MODEL=stub:fenced python main.py "photosynthesis"` → `ok`, exit code 0, 1 log line
`LLM_BASE_URL=local://stub LLM_MODEL=stub:preamble python main.py "photosynthesis"` → `ok`, exit code 0, 1 log line
`LLM_BASE_URL=local://stub LLM_MODEL=stub:malformed python main.py "photosynthesis"` → `invalid_output`, exit code 1, 2 log lines
`LLM_BASE_URL=local://stub LLM_MODEL=stub:badshape python main.py "photosynthesis"` → `invalid_output`, exit code 1, 2 log lines
`LLM_BASE_URL=local://stub LLM_MODEL=stub:empty python main.py "photosynthesis"` → `invalid_output`, exit code 1, 2 log lines
`LLM_BASE_URL=local://stub LLM_MODEL=stub:refused python main.py "photosynthesis"` → `refused`, exit code 1, 1 log line
`LLM_BASE_URL=local://stub LLM_MODEL=stub:error python main.py "photosynthesis"` → `error`, exit code 1, 2 or 3 log lines, all with status error
`LLM_BASE_URL=local://stub LLM_MODEL=stub:flaky python main.py "photosynthesis"` → `ok`, exit code 0, 2 log lines (first status error, then ok)
`LLM_BASE_URL=local://stub LLM_MODEL=stub:ratelimit python main.py "photosynthesis"` → `error`, exit code 1, 2 or 3 log lines, all with status error

Log shape, checked after any run:
- Every line in run_log.jsonl parses as JSON.
- Every line has all nine keys: timestamp, run_id, model, status, prompt_tokens, completion_tokens, latency_ms, cost_usd, tokens_estimated.
- All lines from one run share one run_id.
- Lines with status error have cost_usd null.

Rejected input: `python main.py ""` exits with code 2 and adds no line to run_log.jsonl.

Regression: all eight Lab 4 outcomes still give the same final status and exit code as before logging was added.

`python check.py .`

The checker should complete successfully without reporting failed checks.

# Out of scope

This program will focus only on generating multiple-choice questions through the command line. it will not provide a graphical or web interface or support other types of questions such as short-answer or true/false questions.Features such as user accounts, authentication, databases, storing previous questions, and editing questions manually are also outside the scope of this project.
