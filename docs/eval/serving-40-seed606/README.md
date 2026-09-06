# Meal API review pack — NOT a quality result

Compact handoff: full requests/responses are NOT included; regenerate the full archive for diagnostics.
llm_inputs.jsonl has one profile and final feed per line; keep empty feeds.
It omits archetype, model_score, safety verdict, recipe verified flag and top-level reason codes.
It retains purchase history, explicit preferences, actual offers and saved/offered recipe definitions.
It is not an API-replay request; stock outside the shown offers is omitted.
manifest.json identifies source code, inputs and diagnostic counts.
review.csv is a blank review sheet; keep empty_response rows.
Do not pass the review CSV or manifest to the LLM as profile evidence.
Agree rubric, reviewer, baseline and denominators before computing hit rate.
Returned-meal counts are diagnostics, not relevance or causal uplift.

- Synthetic profiles and inventory; not representative measurements of X5 customers.
- Full current serving catalog, not the mobile three-recipe demo or a new training baseline.
- Cooking profiles only; this inventory generator has no prepared-food SKU. Ready quality is not evaluated.
- Default meal feed after safety, single-store feasibility and selector; no forced mode quotas.
- Empty responses are retained. Quality labels, baseline comparison and hit rate are not computed (D3 pending).
- Offer tokens are replaced with null in the archive; it cannot activate tasks or replay rewards.
- No purchases or rewards are submitted. Purchase history in a request is not verified purchase evidence.
- No causal uplift or economics is measured by this export.
