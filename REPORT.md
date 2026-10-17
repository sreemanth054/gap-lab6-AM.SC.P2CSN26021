# Cost

The measured average was 2.40 model calls per question paper across 5 measured runs. The measured average cost was $0.00063525 per question paper, based on the known costs recorded in the log. At that rate, the estimated cost for 1,000 papers would be $0.63525.

I used an estimated paid-tier price of $0.75 per million input tokens and $3.75 per million output tokens. These prices are the hypothetical prices configured for this lab; the Gemini free tier used for the runs did not charge for these calls.

# Speed

The measured median latency was 2,568 ms per model call, and the measured p95 latency was 11,413.2 ms. The measured slowest call was 11,455 ms.

The slowest calls were not all retries: the 11,455 ms call was a first attempt, while the 11,379 ms call was a retry that eventually succeeded. The rate-limit retries were generally faster, ranging from 2,257 ms to 5,336 ms per call.

# Method

The figures are measured from 12 model-call log entries across 5 question-paper runs. Latency, token usage, and the two successful-call costs were reported by the provider and recorded as measured; failed calls had unknown token usage and cost, so they were recorded as null rather than zero. No token estimation was needed for these real-provider calls because `tokens_estimated` was false.