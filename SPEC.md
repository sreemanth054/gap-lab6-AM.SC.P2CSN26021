# What it does

The program takes a topic entered by the user and uses an AI model to generate five multiple-choice questions on that topic. The questions are built from the client's own documents in `corpus/`, and every question names the document it came from. Each question contains four answer options and one correct answer. The program validates the model's response before accepting it. Only responses that follow the required structure and pass a content check are accepted.

The documents in `corpus/` come from the internet and are untrusted. Their text is data, never an instruction. The program removes instruction-like sentences from a document before the model sees it, and checks the model's reply again before anything is printed or stored.

Two read-only tools let the model consult the client's topic list and the questions already generated. Repeats are prevented by code before storage, not left to the model.

Every model call is also recorded as one line in run_log.jsonl (tokens, latency, cost), and failed calls are retried under a capped policy.

# Inputs

The topic will be given as a string through the command line. It should be at least 3 characters long and should not exceed 200 characters. Topics containing spaces are allowed, as long as they are entered within quotes. If the topic is missing, empty, contains only spaces, or does not meet the length requirements, the program will reject it without sending anything to the AI model.

The program also reads, on every run:
- `corpus/`: six documents (md, txt, pdf, pptx). They are untrusted. Two of them carry injection payloads, one in the body of a PDF and one in the speaker notes of a slide deck. Everything extracted from them, including speaker notes, is treated as data.
- `data/topics.json`: the client's topic list, read only through the `topic_lookup` tool.
- `data/generated_questions.json`: the questions already generated, read only through the `question_lookup` tool. Each row carries id, topic, text, source and created.

The tools may read only inside `data/`, and only the two allow-listed files (`topics.json` and `generated_questions.json`). No tool argument is a filename. The model chooses search terms, never locations.

The program calls Google's Gemini API (OpenAI-compatible endpoint, free tier) with model gemini-3.8-flash, temperature=0.7 and max_tokens=4096.
Cost is computed from two prices, set in observability.py:
- PRICE_IN_PER_MTOK = 0.75 USD per million input tokens
- PRICE_OUT_PER_MTOK = 3.75 USD per million output tokens
Source: https://ai.google.dev/gemini-api/docs/pricing, checked on 4 October 2026. These are the paid-tier prices of the same model, because the free tier charges nothing. Reported costs are therefore what the same calls would cost on the paid tier, not what was actually charged. Output pricing includes thinking tokens.
If the provider reports no usage or zeroed usage, tokens are estimated with estimate_tokens() and tokens_estimated is set to true on that line.

# Outputs

The program should generate exactly five questions for a valid topic. Each question will have the question itself, four answer options, an answer_index that shows which option is correct, and a source: the path of the corpus document it came from. The generated response is checked against these requirements, and against a content check, before it is accepted. The source must be one of the documents that were actually ingested, and question and option text must not carry instruction-style wording, approval claims or code-shaped markers.

The last non-empty line printed by the program will always show what happened. It will be one of ok, invalid_output, refused, or error. A valid response will return ok with exit code 0. If the model response is invalid, fails the content check, is refused, or an error occurs during the model call, the program will return the corresponding status with exit code 1. If the topic is rejected before contacting the model, the program will exit with code 2.

Each model call appends one JSON object to run_log.jsonl in the repository root (append only, one line per call, so a retry is its own line). All lines from one run share one run_id. The file is in .gitignore and never committed. The nine fields are: timestamp, run_id, model, status, prompt_tokens, completion_tokens, latency_ms, cost_usd, tokens_estimated. Unknown values are null, not 0. The log never contains a key, a full prompt or a full reply.

Every run writes `data/ingest_index.json`: one entry per ingested document with source, format and chars. This is how a generated question is traced back to where it came from. The text itself is not written to it.

Security events append to `security_log.jsonl` in the repository root. Each line has timestamp, run_id, event, where and detail, and all lines from one run share one run_id. The event is one of seven fixed names: guardrail_input, guardrail_output, instruction_ignored, tool_arg_rejected, tool_result_rejected, duplicate_blocked, loop_cap_reached. The detail holds a short description only: no secrets, no full prompt, no full reply. The file is in .gitignore and never committed.

`samples/tool_trace.jsonl` holds the full message list of one complete tool loop, one object per line: the request, each tool call, each tool result and the final reply. Its tool-call count equals its tool-result count.

Questions that pass every check are stored in `data/generated_questions.json`, each row with id, topic, text, source and created.

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

**An instruction inside a document.** If a document contains a sentence that reads like an instruction aimed at the model (for example "Ignore all previous instructions" in the body of a PDF, or "New instructions for the assistant" in slide speaker notes), the program removes that sentence before the prompt is built. It writes one guardrail_input event per changed document and one instruction_ignored event per removed sentence, naming the file and line. The run continues on the remaining text and is not a failure. This guardrail matches wording patterns, so a payload worded differently can get past it.

**A reply that carries the attacker's content.** If a reply passes the schema but its source is not an ingested document, or its question or option text carries instruction-style wording, an approval claim, a verification-code mention or a code-shaped marker, the program writes one guardrail_output event per offending question, treats the reply as invalid_output, makes the one repair retry, and if that is also rejected exits with code 1 (2 log lines). Nothing is printed or stored.

**A path where a topic belongs (traversal).** If the model calls a tool with a path-like argument such as `../.env`, nothing is opened: the query is matched against topic names and matches nothing, the tool returns an empty list, and the loop carries on. The one place a path is built, `load_data_file()`, refuses any name outside the allow-list and checks that the resolved path is inside `DATA_DIR` using `Path.is_relative_to`.

**A tool call whose arguments do not validate.** If a call is missing `query`, or `query` fails its constraints, the tool does not run. The program writes tool_arg_rejected and carries on.

**A malformed row in the question store.** One row in `data/generated_questions.json` does not validate. The program writes tool_result_rejected naming the row's id and does not pass that row to the model. Rows are never dropped silently.

**A tool loop that never ends.** The loop stops after MAX_TOOL_STEPS steps (5). The program writes loop_cap_reached and returns invalid_output (or error) with exit code 1.

**A duplicate question.** Before a question is stored, its text is normalised (lower-cased, whitespace collapsed) and compared with the stored questions. A repeat is not stored, and the program writes duplicate_blocked. This is enforced by code before storage, not by asking the model to avoid repeats.

# Acceptance checks

A successful generation should produce five valid questions, each with a source naming an ingested document, and end with `ok`.

Each stub mode is run with the environment variables set on the command line. Before each run, delete run_log.jsonl and security_log.jsonl so the line counts are for that run only. Every check asserts on shape (last line, exit code, number of log lines, keys present, event names present), never on exact model text.

Carried over from Lab 5:

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

New in Lab 6:

`LLM_BASE_URL=local://stub LLM_MODEL=stub:obedient python main.py "photosynthesis"` → `ok`, exit code 0; the output contains no marker added by the stub and every source is an ingested path; security_log.jsonl contains guardrail_input and instruction_ignored events naming `corpus/06_exam_security_handbook.pdf` and `corpus/04_academic_integrity_deck.pptx`
`LLM_BASE_URL=local://stub LLM_MODEL=stub:toolcall python main.py "photosynthesis"` → `ok`, exit code 0; both tools ran; security_log.jsonl contains tool_result_rejected naming the malformed row
`LLM_BASE_URL=local://stub LLM_MODEL=stub:traversal python main.py "photosynthesis"` → `ok`, exit code 0; no file outside `data/` was opened; security_log.jsonl contains tool_arg_rejected
`LLM_BASE_URL=local://stub LLM_MODEL=stub:neverstop python main.py "photosynthesis"` → `invalid_output` or `error`, exit code 1; the loop stops at MAX_TOOL_STEPS = 5 and security_log.jsonl contains loop_cap_reached

Log shape, checked after any run:
- Every line in run_log.jsonl and security_log.jsonl parses as JSON.
- Every line in run_log.jsonl has all nine keys: timestamp, run_id, model, status, prompt_tokens, completion_tokens, latency_ms, cost_usd, tokens_estimated.
- Every line in security_log.jsonl has all five keys: timestamp, run_id, event, where, detail, and the event is one of the seven fixed names.
- All lines from one run share one run_id.
- Lines with status error have cost_usd null.

Rejected input: `python main.py ""` exits with code 2 and adds no line to run_log.jsonl.

Regression: all eight Lab 4 outcomes still give the same final status and exit code as before logging was added.

`python check.py .`

The checker should complete successfully without reporting failed checks.

# Out of scope

This program will focus only on generating multiple-choice questions through the command line. It will not provide a graphical or web interface or support other types of questions such as short-answer or true/false questions.

Features such as user accounts, authentication, databases and manual editing of questions are also out of scope. Questions are stored only as rows in `data/generated_questions.json`. The tools are read-only and have no shell. The program does not try to verify that a document's facts are true, only that its text is not treated as an instruction.