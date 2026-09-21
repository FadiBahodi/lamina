# A stalled report and a dangerous retry

Original SAMP-style short-answer practice for the supplied teaching material. This is not an official examination item or a validated score.

## Candidate sheet

Answer one prompt before reading the next line of new information. Keep the examiner sheet closed.

### Recover without duplicate publication

A scheduled report appears stalled. Its worker's lease has expired, and an operator is ready to start a replacement.

**Question 1 — 2 marks; give at most 2 answers.** Give two separate conclusions about what lease expiry permits and what it cannot establish.

_Answer:_

____________________________________________________________

**New information for question 2:** Worker B claims the job. Worker A then returns with a completed report.

**Question 2 — 2 marks; give at most 2 answers.** State the commit check and the disposition of A's result.

_Answer:_

____________________________________________________________

**New information for question 3:** The replacement attempts publication, then loses the reply. The report may already be public when it retries.

**Question 3 — 2 marks; give at most 2 answers.** Name two distinct safeguards needed before the retry can perform the publication effect.

_Answer:_

____________________________________________________________

**New information for question 4:** The retry carries changed report parameters but reuses the earlier idempotency key.

**Question 4 — 2 marks; give at most 2 answers.** What should the workflow decide about that key, and why?

_Answer:_

____________________________________________________________


---

## Examiner sheet

The point allocations are an original practice rubric. Critical errors are review flags, not automatic deductions.

### Recover without duplicate publication

**Question 1: 2 marks**

- **1 mark:** A replacement may claim the expired job. (01-leases.md · Leases make stalled work recoverable · lines 4–7 — “after expiry, another worker may claim the job.”)
- **1 mark:** Expiry does not prove the original worker stopped. (01-leases.md · Leases make stalled work recoverable · lines 4–7 — “Expiry means ownership is uncertain, not that the first worker stopped.”)

Critical-error flags:
- Treating expiry as proof that the old worker cannot finish. (01-leases.md · Leases make stalled work recoverable · lines 4–7 — “Expiry means ownership is uncertain, not that the first worker stopped.”)

**Question 2: 2 marks**

- **1 mark:** Compare A's owner token with the current job token at commit. (01-leases.md · Leases make stalled work recoverable · lines 4–7 — “Every completion checks that its token still matches the job's current lease.”)
- **1 mark:** Reject A's result for publication if its token is stale. (01-leases.md · Leases make stalled work recoverable · lines 4–7 — “If the token changed, the stale result is discarded or saved only for diagnosis.”)

Critical-error flags:
- Publishing A's result solely because its computation finished. (01-leases.md · Leases make stalled work recoverable · lines 4–7 — “If the token changed, the stale result is discarded or saved only for diagnosis.”)

Decision change: Recovery is now a stale-writer problem: only the current owner may commit.

**Question 3: 2 marks**

- **1 mark:** Use a stable idempotency key for this intended publication. (02-idempotency.md · Idempotency contains retries · lines 4–7 — “An idempotency key names one intended operation across retries.”)
- **1 mark:** Check durable completion at the publication side-effect boundary. (02-idempotency.md · Idempotency contains retries · lines 4–7 — “Put the idempotency check at the side-effect boundary, such as charging a card or publishing an artifact.”)

Critical-error flags:
- Replaying publication blindly because no reply was received. (02-idempotency.md · Idempotency contains retries · lines 4–7 — “a repeated request returns the same result instead of repeating the side effect.”)

Decision change: Ownership alone no longer settles safety; the effect may have occurred before the reply was lost.

**Question 4: 2 marks**

- **1 mark:** Do not treat changed meaningful inputs as the same intended operation. (02-idempotency.md · Idempotency contains retries · lines 4–7 — “The key must include the operation's meaningful inputs; reusing a key for different inputs creates a false match.”)
- **1 mark:** Use a distinct intent identity or surface an explicit conflict before publication. (02-idempotency.md · Idempotency contains retries · lines 4–7 — “The key must include the operation's meaningful inputs; reusing a key for different inputs creates a false match.”)

Critical-error flags:
- Returning the earlier outcome for a changed operation without checking identity. (02-idempotency.md · Idempotency contains retries · lines 4–7 — “The key must include the operation's meaningful inputs; reusing a key for different inputs creates a false match.”)

Decision change: The retry is no longer equivalent to the original operation; identity must be resolved before reuse.

Teaching explanation:

A lease opens recovery, while the current owner token fences a late writer. A lost reply introduces a different uncertainty: the external effect may already have happened. The idempotency check therefore belongs at the publication boundary and its key must include inputs that change intent. The marks describe this original practice rubric; critical errors are review flags, not an automatic penalty rule.
