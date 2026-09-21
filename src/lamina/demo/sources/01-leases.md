# Resilient workflow engineering

## Leases make stalled work recoverable

A lease grants one worker temporary ownership of a job until a recorded expiry. The worker renews it while making progress; after expiry, another worker may claim the job. Expiry means ownership is uncertain, not that the first worker stopped. A late worker can still finish after its lease expires.

An owner token prevents a late worker from publishing over a newer attempt. Every completion checks that its token still matches the job's current lease. If the token changed, the stale result is discarded or saved only for diagnosis. A heartbeat reports liveness; it does not replace the ownership check.
