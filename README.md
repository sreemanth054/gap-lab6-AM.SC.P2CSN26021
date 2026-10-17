# Lab 6 starter

Drop these files into your Lab 6 repository **on top of** your Lab 5 work.
They replace `client.py`, `stub_client.py`, `check.py`, `.gitignore`,
`.env.example` and `requirements.txt`, and add seven new things.

`SPEC.md`, `DECISIONS.md`, `QUESTION.md`, `REPORT.md`, `observability.py`,
`main.py` and `samples/*.json` are deliberately **not** in this zip, so that
copying it over your Lab 5 repository cannot destroy your own work. Your
prices in `observability.py` survive.

| File | Yours? |
|---|---|
| `client.py` | No. Do not edit. Identical to the Lab 4 and Lab 5 file |
| `stub_client.py` | No. Do not edit. Now fourteen modes, not ten |
| `check.py` | No. The same script used for marking. Run it on yourself |
| `doc_loader.py` | **Supplied, and yours to edit.** Reads the corpus. Never rename the four keys |
| `security.py` | **Supplied, and yours to edit.** Never rename the five keys or invent event names |
| `tools.py` | **Supplied as signatures. Five TODOs.** The two tool names, the model names and `get_tool_schemas()` are fixed. Read TODO 1 first |
| `corpus/` | No. Six documents. **Two are poisoned** |
| `data/topics.json` | No. The topic list the client keeps elsewhere |
| `data/generated_questions.json` | Grows. **One row is malformed on purpose** |
| `ATTACK.md` | Yes. Fill it in. The headings are what is marked |
| `SECURITY.md` | Yes. Six fixed headings, and they carry into the capstone |
| `.gitignore` | Replaces the Lab 5 one. Adds `security_log.jsonl` |
| `.env.example` | Copy to `.env` and fill in. Never commit `.env` |
| `samples/tool_trace.jsonl` | Yes. Create it. One complete loop |

## Start

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
cp .env.example .env
```

## Run

```bash
python main.py "Assessment design and item writing"
```

## Check yourself

```bash
python check.py .
```

It runs your program in a throwaway copy of your repository, so it cannot
damage your work, your logs or your question store.

## The fourteen stub modes

The ten you already have, unchanged:

```
stub:ok  stub:fenced  stub:preamble  stub:malformed  stub:badshape
stub:empty  stub:refused  stub:error  stub:flaky  stub:ratelimit
```

Four new ones:

```
stub:obedient  stub:toolcall  stub:traversal  stub:neverstop
```

`stub:obedient` matches on instruction **phrasings** and generates the marker
it appends itself, so deleting a string out of a document does not stop it
obeying.

`stub:traversal` sends a file path where a topic name belongs, and then a call
with the required argument missing. One of those is contained by design and the
other is refused by your argument model. Neither is fixed by a cleverer check
on the string.

`stub:neverstop` has its own hard cap of 50 calls so a marking run cannot hang;
yours belongs a long way below that, in `MAX_TOOL_STEPS`.

## Two warnings

**The corpus is untrusted.** Everything `doc_loader` hands you is text somebody
else wrote, in documents pulled off the internet. It is data. It is never an
instruction. Speaker notes and footers are extracted on purpose: a human
skimming the deck will not see them, and your program will.

**A guardrail that writes no line to `security_log.jsonl` is a guardrail that,
as far as marking is concerned, never ran.**

Read the assignment brief for what is fixed, what is yours, and how it is marked.
