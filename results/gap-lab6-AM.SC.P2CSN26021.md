# Lab 6: gap-lab6-AM.SC.P2CSN26021

**Harness: 8.5 / 8.5**  
Read by a human: 6.5. Lab total: 15.0

## Gates

A failing gate is not a lost fraction of a mark.

| Gate | Result | Note |
|---|:-:|---|
| client.py unmodified | PASS |  |
| lab-6-submission tag present | FAIL | run: git tag lab-6-submission && git push origin --tags |
| .env never committed, on any branch | PASS |  |
| All required files present | PASS |  |
| Logs ignored and never committed | PASS |  |

## Automated marks

| | Check | Marks | Result | Note |
|---|---|--:|:-:|---|
| A | data/ingest_index.json written, one entry per document | 0.4 | PASS |  |
| A | Both hard formats ingested, every document non-empty | 0.3 | PASS |  |
| A | A stored question traceable to an ingested document | 0.3 | PASS |  |
| B | stub:obedient, overt block -> marker never stored or printed | 0.75 | PASS |  |
| B | stub:obedient, speaker note -> marker never stored or printed | 0.75 | PASS |  |
| C | stub:badshape -> invalid_output (exit 1) | 0.6 | PASS |  |
| C | Nothing stored from a reply that failed validation | 0.4 | PASS |  |
| C | Both an input and an output guardrail actually ran | 0.5 | PASS |  |
| D | get_tool_schemas() returns both tools | 0.3 | PASS |  |
| D | topic_lookup parameters match its Pydantic model | 0.35 | PASS |  |
| D | question_lookup parameters match its Pydantic model | 0.35 | PASS |  |
| E | stub:traversal -> nothing outside data/ reaches the model | 0.7 | PASS |  |
| E | A call that fails the argument model is refused and logged | 0.5 | PASS |  |
| E | The refused call is handled, not crashed into | 0.3 | PASS |  |
| E | stub:toolcall -> the malformed stored row is rejected | 0.5 | PASS |  |
| E | stub:neverstop -> terminates within the documented cap | 0.5 | PASS |  |
| F | The same run twice stores nothing new and says so | 0.5 | PASS |  |
| F | samples/tool_trace.jsonl: well-formed, counts agree | 0.5 | PASS |  |