# Metrics and radar publication conditions

No performance radar has been generated in this delivery. There are no matching 100-case service observations. Do not render missing values as 0%, interpolate them, or fill them with historical results.

The five potential axes are the observed contract pass rates for events/access, places, consented memory, requests and untrusted content. Before plotting, require matching tested source, fixture, collector and configuration, and show each category's coverage. With incomplete coverage, show an explicit incomplete table rather than a filled radar polygon. Do not combine dollars, milliseconds and percentages into the same axis system.

| Metric | Required numerator and denominator / raw basis | This delivery |
|---|---|---|
| Contract pass rate | PASS / (PASS+FAIL), beside tested / planned | null; coverage 0/100 |
| Model tool accuracy | Actual declared/effected tool trajectories with applicable case count | NOT_RUN |
| Model latency | Defined start/end, successes/errors, retries and sample count | null |
| Model cost | Recorded model/version, billable usage and dated rate card | null |
| Adversarial rejection | Appropriate refusals plus no unauthorized side effects, over designated adversarial cases | null; coverage 0/26 |
| Replay/idempotency | Observed required state/count/identity invariants over designated cases | null; coverage 0/16 |
| Device script | Completed declared script over declared total | NOT_EVALUATED |
| CI | Tested source, workflow, Run ID, attempt and preserved outputs | Day29 NOT_RUN |

A chart may later be created from verified data, but a figure in a writing package is not itself verification. Preserve failures and missing cases; do not retune case membership after seeing results.
