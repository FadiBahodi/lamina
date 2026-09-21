# Short-answer management problems

Lamina's SAMP-style output is a **separate production path** from its oral scenario. A problem presents a short stem, then three to five numbered prompts. Later prompts reveal new information and require a changed decision. Each prompt has an explicit answer limit and mark allocation. A separate examiner sheet lists independently creditable answer points, exact teaching-source receipts, critical-error flags, and a teaching explanation. The flags invite review; Lamina does not apply an automatic penalty rule.

The [public example](../examples/samp/samp.md) is an original workflow-engineering incident. It is neither medical content nor an official examination item. The term “SAMP-style” describes a short-answer practice shape; it makes no claim of examination equivalence or validated scoring.

## Generate and export

`generate_samp(bundle, provider, workspace, procedure=None)` validates the learning bundle, then runs a distinct, cached `samp` stage. The command adapter receives a `lamina-samp-1` JSON request with teaching sources, units, canonical concepts, and an optional validated procedure context (audience, instructions, selected outputs, revision). The procedure must select `samp`; its context participates in the cache key. Assessment-role material is absent because it is excluded from the validated bundle. The adapter returns a title and one to three problems. Lamina injects the referenced teaching sources, units, and concepts, then validates the result. A separate, cached `samp_review` adapter request receives the complete artifact, its evidence, and the same procedure context. Its response uses `{ "status": "pass" | "revise", "issues": [{ "detail": "..." }] }`; `revise` blocks the artifact from being returned. This review is a second adapter reading, not independent expert certification.

```python
from pathlib import Path
from lamina.samp import generate_samp, export_samp

artifact = generate_samp(bundle, provider, workspace)
json_path, markdown_path = export_samp(artifact, Path("./short-answer-practice"))
```

The offline `DemoProvider` uses one curated original engineering problem for its exact bundled field guide and an explicitly curated passing review response. It does not generate or review arbitrary problems, and the fixture is unchanged by a procedure's wording. A configured command adapter must implement both `samp` and `samp_review` for other material. Both stage requests retain Lamina's JSON-over-standard-input/standard-output convention; see [Adapters](adapters.md). The callable API is usable independently of any particular UI.

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

The abbreviated example shows the field names, not a valid full problem: validation requires three to five steps. The first step has no new information or decision-change field content; each later step requires both. IDs must be unique in their scope. Each answer point earns one to three marks, the step's marks equal the sum of its points, and the answer limit must allow all listed points. A problem has at most 36 marks. Critical errors need exact evidence but are not part of that arithmetic.

Evidence must quote a known teaching unit owned by a canonical concept assigned to the problem. An answer may use a more precise passage from that unit than the quote chosen during concept extraction; it cannot use a different unit merely because the words sound relevant. This structural rule still cannot prove that the passage supports the answer. Unknown fields are rejected, including private notes that could otherwise leak into public JSON. The exported `samp.json` carries the units belonging to referenced concepts; `samp.md` places the candidate sheet before a separate examiner sheet. Every export revalidates the artifact.

## What the checks mean

The validator proves source-ID membership, exact quote occurrence, source-to-concept ownership, response limits, and consistent mark totals. It does not decide whether an answer follows from its quote, whether two answer points are truly independent, whether the stem is fair, or whether the changed information would elicit the intended reasoning from a learner. The `samp_review` stage asks the configured adapter to assess those semantic properties and blocks its stated failures; its passing response is not a ground-truth guarantee. A human should review generated problems before consequential assessment. The public example demonstrates the production contract and candidate/examiner separation, not measured learning or score validity.
