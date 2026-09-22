# Short-answer management problems

SAMP-style output is a separate path from Lamina's oral scenario. Each problem has a short stem and three to five numbered prompts. Later prompts reveal information that changes the decision. Prompts set answer limits and marks. A separate examiner sheet gives independently creditable answer points, exact teaching-source receipts, critical-error flags, and an explanation. Flags invite review; Lamina applies no automatic penalty rule.

The [public example](../examples/samp/samp.md) is an original workflow-engineering incident. "SAMP-style" describes the practice format, not an official examination item or validated scoring.

## Generate and export

`generate_samp(bundle, provider, workspace, procedure=None)` validates the learning bundle and runs a cached `samp` stage. Its `lamina-samp-1` request contains teaching sources, units, canonical concepts, and optional validated procedure context: audience, instructions, outputs, and revision. The procedure must select `samp`, and its context enters the cache key. Assessment-role material is absent from the bundle. The adapter returns a title and one to three problems. Lamina injects referenced teaching sources, units, and concepts, then validates the result. A cached `samp_review` call receives the complete artifact, evidence, and procedure context. It returns `{ "status": "pass" | "revise", "issues": [{ "detail": "..." }] }`; `revise` blocks return.

```python
from pathlib import Path
from lamina.samp import generate_samp, export_samp

artifact = generate_samp(bundle, provider, workspace)
json_path, markdown_path = export_samp(artifact, Path("./short-answer-practice"))
```

The offline `DemoProvider` supplies one curated engineering problem and a passing review response for the bundled field guide. It neither generates nor reviews arbitrary problems, and procedure wording does not change its fixture. A command adapter for other material must handle both `samp` and `samp_review` using JSON over standard input/output; see [Adapters](adapters.md). The Python API works without the UI.

## Response shape

```json
{
  "title": "A short problem-set title",
  "problems": [{
    "id": "incident-1",
    "title": "A problem title",
    "stem": "A concise initial situation.",
    "concept_ids": ["known-canonical-concept-id"],
    "steps": [{
      "id": "q1",
      "new_information": null,
      "prompt": "Give two independent decisions or reasons.",
      "answer_limit": 2,
      "marks": 2,
      "answer_points": [
        {"id": "a1", "answer": "One independently creditable point.", "marks": 1,
         "evidence": [{"unit_id": "known-teaching-unit-id", "quote": "Exact source text"}]},
        {"id": "a2", "answer": "A distinct point.", "marks": 1,
         "evidence": [{"unit_id": "known-teaching-unit-id", "quote": "Exact source text"}]}
      ],
      "critical_errors": [{"id": "e1", "text": "An unsafe shortcut to flag for review.",
                           "evidence": [{"unit_id": "known-teaching-unit-id", "quote": "Exact source text"}]}],
      "decision_change": null
    }],
    "teaching_explanation": "Explain why the decisions change across the sequence."
  }]
}
```

This abbreviated shape is not a valid full problem: validation requires three to five steps. The first has no new information or decision change; later steps require both. IDs are unique in their scope. Answer points earn one to three marks each; step marks equal their sum, and the answer limit must accommodate all points. Problems have at most 36 marks. Critical errors need exact evidence but do not enter mark arithmetic.

Evidence must quote a known teaching unit owned by a canonical concept assigned to the problem. An answer may cite a more precise passage from that unit than extraction did, but not a different unit with similar words. Unknown fields, including private notes that could leak into public JSON, fail validation. `samp.json` carries units for referenced concepts; `samp.md` puts the candidate sheet before the examiner sheet. Export revalidates the artifact.

## Limits

Validation checks source and concept ownership, quote occurrence, response limits, and mark totals. It cannot determine whether a quote supports an answer, points are independent, a stem is fair, or new information elicits the intended reasoning. `samp_review` asks the configured adapter to judge those properties and blocks its stated failures; a pass is not expert certification. Review generated problems before consequential assessment. The public fixture shows the production contract and sheet separation, not learning or scoring validity.
