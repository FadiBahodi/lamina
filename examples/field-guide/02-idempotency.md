# Resilient workflow engineering

## Idempotency contains retries

An idempotency key names one intended operation across retries. A durable result store maps the key to the completed outcome, so a repeated request returns the same result instead of repeating the side effect. The key must include the operation's meaningful inputs; reusing a key for different inputs creates a false match.

At-least-once delivery means a job may run twice after a timeout or crash. A lease reduces overlap, but it cannot prove exactly-once execution. Put the idempotency check at the side-effect boundary, such as charging a card or publishing an artifact. Cache a successful model response separately from committing an external effect.
