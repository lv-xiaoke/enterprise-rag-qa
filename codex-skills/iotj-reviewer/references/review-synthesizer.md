# Review Synthesizer: IoT-J AE View

Use this when the input contains 3-4 reviewer reports, recommendations, reviewer comments, or an AE summary request.

## Recommendation Scale

- `Reject`: reject, normally not invited for resubmission.
- `Major Revision`: large proof/model/experiment/baseline changes are needed.
- `Minor Revision`: core paper is accepted in principle; only polishing or small clarifications remain.
- `Accept`: direct acceptance; rare in first round.

## Required Dimensions

For each reviewer:

1. Classify credibility:
   - `Math/Optimization Expert`: identifies formula derivation, constraint, convergence, complexity, or theorem problems.
   - `System/Networking Expert`: challenges simulation realism, MAC/PHY settings, traffic model, energy model, or testbed validity.
   - `Shallow/Generic`: generic praise or criticism, language-only comments, citation shopping, or signs of weak understanding.
2. Detect empty praise:
   - If recommendation is `Minor Revision` or `Accept` but comments are under about 150 words or only request self-citations, set type to `Empty_Praise` and down-weight credibility.
3. Reward hard criticism:
   - If recommendation is `Reject` or `Major Revision` and the reviewer identifies specific equations, assumptions, impossible parameters, missing baselines, or simulation flaws, set type to `High_Credibility_Critical`.
4. List fatal flaw allegations:
   - Track who claimed the issue, issue type, concrete detail, and location.
5. Quantify consensus:
   - `Strong Consensus`
   - `Split (Theory vs. System)`
   - `Split with Credible Low`
6. Select the most dangerous issue:
   - `Unresolved_Math_Error`
   - `Unrealistic_System_Assumption`
   - `Weak_Baselines/Simulation`
   - `Out_of_Scope`
   - `No_Credible_Fatal_Flaw`
7. Predict revision feasibility, especially whether requested experiments or proofs can realistically be added in a journal major-revision window.
8. Produce one AE-style synthesis sentence.

## Output JSON

Return strict JSON with exactly these top-level keys:

{
  "reviewer_analysis": {
    "Reviewer 1": {
      "credibility": "Math/Optimization Expert | System/Networking Expert | Shallow/Generic",
      "type": "Empty_Praise | High_Credibility_Critical | Credible_Constructive | Generic_Critical",
      "recommendation": "Reject | Major Revision | Minor Revision | Accept | Unknown",
      "critic": [
        "brief assessment of attitude, expertise, and main criticism"
      ]
    }
  },
  "fatal_flaw_allegations": [
    {
      "reviewer": "Reviewer 1",
      "type": "Unresolved_Math_Error | Unrealistic_System_Assumption | Weak_Baselines/Simulation | Out_of_Scope | Other",
      "detail": "specific allegation",
      "location": "equation, section, figure, table, or Unknown"
    }
  ],
  "most_dangerous_issue": "Unresolved_Math_Error | Unrealistic_System_Assumption | Weak_Baselines/Simulation | Out_of_Scope | No_Credible_Fatal_Flaw",
  "consensus_type": "Strong Consensus | Split (Theory vs. System) | Split with Credible Low | Weak/No Consensus",
  "risk_level": "High | Medium | Low",
  "meta_review_one_liner": "one sentence AE synthesis"
}

Do not invent reviewer identities. Use labels from the input, or `Reviewer 1`, `Reviewer 2`, etc.
