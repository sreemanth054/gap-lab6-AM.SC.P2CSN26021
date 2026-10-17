## 2026-10-04 - Add bounded retries for model errors

During Checkpoint 4, I added retry handling for model errors. A failed model call can now be retried up to three attempts, with exponential backoff, jitter, and support for the provider's `Retry-After` value.

I could have retried only once for every error, but that would not match the required error policy. I also could have retried indefinitely, but that could lead to unbounded model calls and cost. I chose the bounded three-attempt approach.

## 2026-10-04 - Add exactly one repair retry for invalid output

I added a separate repair retry for `invalid_output`. When the first response cannot be parsed or fails Pydantic validation, the program makes exactly one additional model call with an instruction to return only valid JSON.

I could have treated invalid output as a final failure immediately, but that would unnecessarily discard responses that could be fixed with a simple repair prompt. I also rejected repeated repair attempts because they could cause unnecessary model calls and spending.

## 2026-10-04 - Test retries and failure handling with the stub

I tested the new retry behavior using the stub modes `flaky`, `ratelimit`, `malformed`, `badshape`, and `empty`. I also verified that refusals are not retried and that normal `ok`, `fenced`, and `preamble` responses still require only one model call.

I could have tested only the normal successful response, but that would not demonstrate that the retry limits and repair behavior actually work. The tests confirmed that every attempt is logged and that the expected final status is returned.