# Current worker procedure

A retry obtains a new fencing token before writing. Storage rejects writes carrying an older token. Lease expiry alone does not prove that the former worker stopped.
