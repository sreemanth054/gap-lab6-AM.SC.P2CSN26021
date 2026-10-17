## 2026-10-17: Remove instruction-like sentences by wording pattern

**Decision:** `sanitise_document` removes any sentence matching one of nine instruction patterns before the prompt is built, and logs `guardrail_input` and `instruction_ignored` with the file and line.
**Rejected:** deleting the two exact payload strings, and relying on a prompt line that says the documents are untrusted. stub:obedient generates its marker itself and matches phrasings, so removing a string does not stop it, and no prompt wording changes what it does.
**Cost:** a reworded payload can pass, and a legitimate sentence that matches a pattern is deleted.

## 2026-10-17: Check the reply's content after the schema passes

**Decision:** `check_paper` rejects a reply whose `source` is not an ingested document, or whose question or option text carries instruction wording, an approval claim, a "verification code" mention or a code-shaped marker. A rejected reply gets the one repair retry.
**Rejected:** trusting the Pydantic schema alone. The poisoned replies were valid JSON and the run ended `ok`.
**Cost:** a wrong `source` that is a real ingested path still passes.

## 2026-10-17: A tool argument is a search term, never a path

**Decision:** neither tool takes a filename. `load_data_file` is the only place a path is built, from a name in my own code, checked against `ALLOWED_FILES`, resolved, then tested with `Path.is_relative_to`.
**Rejected:** letting the model pass a file name and checking the string with `startswith`, which is also true for `data_backup`.
**Cost:** the tools can only search the two stored files.

## 2026-10-18: Ignore extra tool arguments instead of forbidding them

**Decision:** the argument models use Pydantic's default, so an unexpected field is ignored and only `query` and `limit` are ever read.
**Rejected:** `extra="forbid"`, which I added first. stub:toolcall and stub:neverstop send `{"query": ..., "source": "topics.json"}`, so forbidding it would refuse the call and the tool would never run.
**Cost:** a bad extra field is not logged.

## 2026-10-18: Block duplicates in code before storage

**Decision:** `store_questions` compares each question's text, lower-cased, with the stored rows, skips a repeat and logs `duplicate_blocked`.
**Rejected:** relying on the model to call `question_lookup` and avoid repeats. A model can forget to check, and only code makes a repeat impossible.
**Cost:** a repeat with different wording is stored.