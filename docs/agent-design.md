# Web Agency OS — Agent Design

Revision: Phase 0, corrected after the Phase 0 review ([phase0-review.md](phase0-review.md)). Date: 2026-10-19.
Status: **design for later phases. M1 and M2 contain no agents and no AI.** Each agent below requires its phase to be
approved, an LLM provider and a user-set cap (PD-18). Token envelopes and eval thresholds are HYPOTHESIS (P-25, P-29).
See [architecture](architecture.md) and [data-contracts](data-contracts.md).

## 1. Design rules

1. **Agents propose, code decides.** An agent's output is a proposal validated against a JSON Schema and invariants. Only
   the workflow engine changes state; only the budget service authorizes spend; only the approval service executes
   approved actions.
2. **One bounded task per invocation.** No long-lived autonomous agents, no free agent-to-agent conversation.
3. **Deterministic first.** Anything measurable or rule-based (performance, accessibility, HTTPS, site facts, scoring,
   contactability, prices, QA pass/fail) is code.
4. **No shell, no filesystem, no raw network.** These tools are not in the registry, so no prompt can unlock them.
5. **Untrusted content is data.** Fetched pages, documents and inbound messages are passed inside delimited,
   provenance-labelled blocks. Agents receiving untrusted content have no external-write tool and no secret.
6. **Every claim is anchored** to an `evidence_id` or `finding_id`; textual evidence needs a snippet found literally in
   the stored capture (checked in code).
7. **No agent sets `purchase_intent`, contactability, a bucket or a state** (D-021, D-023).
8. **Versioned and evaluated.** `agent@version` = prompt template hash + output schema version + model tier.

## 2. What is deterministic, what an agent may do, what a person decides

| Deterministic code | Agent (proposes only) | Person |
|---|---|---|
| Measurements, findings, basic site facts, three-layer assessment, gates | Read the business's own pages and extract claims with literal snippets | Approve shortlists, campaigns, previews, contacts, budget changes, publication |
| State transitions, budget, permissions, approvals | Explain measured findings in plain Spanish, citing each finding | Resolve ambiguous identity and conflicting evidence |
| Contactability (later, per counsel), suppression, opt-out | Propose page structure, copy and component selection | Record interactions with prospects (the only source of `purchase_intent`) |
| Prices, schema validation, QA pass/fail, builds, exports | Advisory visual critique of screenshots (never a gate) | Design review; legal sign-off |

## 3. LLM agents (later phases)

Model tiers (`small`, `medium`, `vision`) map to provider models by configuration once a provider is chosen (U-1).

**Initial set when agents are first approved:** A4 (research) and A3 (diagnosis narrative) in M5. All others wait for
their phases.

| # | Agent | Purpose | Output schema | Reads untrusted content? | Envelope (HYPOTHESIS, P-25) | Phase |
|---|---|---|---|---|---|---|
| A1 | `discovery_planner` | Query proposals for approved sources | `DiscoveryPlanProposal` | No | 4k / 1k tokens, 2 tool calls | M4 (optional) |
| A2 | `business_classifier` | Category proposal; always `INFERRED` | `ClassificationProposal` | Yes | 2k / 0.3k, 0 | M4 (optional) |
| A3 | `diagnosis_narrator` | Plain-language explanation of findings; cannot add findings | `DiagnosisNarrative` | Structured values only | 4k / 1k, 0 | M5 |
| A4 | `business_researcher` | Claims from the business's own pages, with literal snippets | `EvidenceProposal[]`, `ResearchDossier` | Yes | 25k / 3k, ≤ 10 fetches | M5 |
| A5 | `website_strategist` | Scope, pages, conversion goal, sections | `WebsiteStrategy` | Validated claims only | 8k / 2k, 2 | M7 |
| A6 | `copywriter` | Spanish copy; facts cite evidence | `CopyDeck` | Validated claims only | 10k / 4k, 0 | M7 |
| A7 | `art_director` | Theme, palette roles, type pair, imagery slots, motion preset | `CreativeBrief` | No | 5k / 1k, ≤ 5 library searches | M7 |
| A8 | `site_assembler` | Typed site manifest from catalogue components | `WebsiteProjectManifest` | No | 12k / 6k, ≤ 3 validations | M6b |
| A9 | `qa_reviewer` | Advisory visual critique; never a gate | `VisualReview` | No (own artifacts) | 4 images + 3k / 1k | M6b |
| A10 | `sales_preparer` | Drafts (summary, proposal outline, call script, letter); nothing is sent | `SalesPackage` | Validated claims only | 8k / 3k, 2 | M8 |
| A11 | `reply_triage` | Classify inbound replies into proposals; opt-outs handled conservatively by code | `ReplyClassification` | Yes | 3k / 0.3k, 0 | Deferred |
| A12 | `delivery_assistant` | Change requests → manifest diffs | `ManifestDiffProposal` | Yes | 10k / 4k, 1 | Deferred |

### 3.1 Per-agent guardrails (enforced in code)

| Agent | Constraints |
|---|---|
| A1 | Only sources enabled after review; output count within quota; human approves the campaign plan. |
| A2 | `claim_status` forced to `INFERRED`; cannot satisfy a gate by itself. |
| A3 | Every sentence references ≥ 1 `finding_id`; findings with `sales_safe = false` excluded from sales text; impact is always worded as a hypothesis. |
| A4 | Fetch restricted to the lead's registrable domain, GET only, page limit; `KNOWN` only with a literal snippet (else downgraded to `UNKNOWN` and logged); contact values only if literally present; no data about individuals beyond business contact details published by the business. |
| A5 | Scope within tier limits; must state which findings each choice addresses; catalogue components only. |
| A6 | Claim detector: digits, years, counts, certifications, awards, ratings, guarantees, superlatives, prices and testimonials must link to evidence or the block is rejected; testimonials never generated; placeholders through `Placeholder`. |
| A7 | Approved fonts only; assets only with compatible `usage_scope`; contrast checked by code. |
| A8 | Per-component schema validation; no raw HTML, scripts or external URLs except evidence-backed contact links. |
| A9 | Advisory only; disagreements logged for evaluation. |
| A10 | Mandatory notices verbatim from the compliance template store (content PENDING counsel); prices only from the price table; claims state measurement date and tool; no email draft without a consent record; nothing is sent. |
| A11/A12 | No tools; outputs reviewed by a person. |

## 4. Tool permission model (later phases)

### 4.1 Tool classes

| Class | Meaning | Who may call |
|---|---|---|
| `R-INT` | Read internal data scoped to the task's lead/project | Agents per matrix |
| `R-WEB` | Fetch public web via the fetcher (robots, rate limit, SSRF guard, scope) | A4 only |
| `P-INT` | Propose internal records (validated before persistence) | Agents per matrix |
| `M-PAID` | Metered APIs (the LLM, stock library) — reservation mandatory | Runner; A7 (stock search) |
| `C-SBX` | Sandboxed compute (audit, build, QA) | Workflow engine only |
| `X-EXT` | External write / outward-facing | **No agent.** Approval service after a human decision |
| `SYS` | Shell, filesystem, arbitrary HTTP, code execution, package installation | **Does not exist** |

### 4.2 Permission matrix

✔ allowed · ✖ not available · ◐ restricted (see §3.1)

| Agent | R-INT | R-WEB | P-INT | M-PAID | C-SBX | X-EXT | SYS | Human approval of output |
|---|---|---|---|---|---|---|---|---|
| A1 | ✔ | ✖ | ✔ | LLM | ✖ | ✖ | ✖ | Yes (campaign plan) |
| A2 | ✖ | ✖ | ✔ | LLM | ✖ | ✖ | ✖ | Ambiguous cases to review |
| A3 | ✔ | ✖ | ✔ | LLM | ✖ | ✖ | ✖ | Before any external use |
| A4 | ✔ | ◐ | ✔ | LLM | ✖ | ✖ | ✖ | Conflicts and gate-relevant claims to review |
| A5–A7 | ✔ | ✖ | ✔ | LLM (A7 ◐ stock) | ✖ | ✖ | ✖ | Via preview approval; designer review |
| A8 | ✔ | ✖ | ✔ | LLM | requests only | ✖ | ✖ | Via QA gates + designer review |
| A9 | ✔ | ✖ | ✔ | LLM (vision) | ✖ | ✖ | ✖ | Advisory only |
| A10 | ✔ | ✖ | ✔ | LLM | ✖ | ✖ | ✖ | Yes (per contact) |
| A11, A12 | ✖ / ✔ | ✖ | ✔ | LLM | ✖ | ✖ | ✖ | Yes |

### 4.3 Gateway enforcement per call

1. Caller identity `agent@version` bound to `task_id`; tool in the task's allowlist.
2. Arguments validated; URLs checked against scope and SSRF rules; GET/HEAD only.
3. Policy check → allow / deny (reason) / require approval.
4. Budget reservation for metered tools; denial if any cap would be exceeded.
5. Execution with timeout and size limits; raw result stored by hash; sanitized, labelled view returned.
6. Event `tool.call_completed` or `tool.call_denied` written by the gateway.

## 5. Agent runner contract

```text
TaskEnvelope {
  task_id, run_id, lead_id?, project_id?,
  agent, agent_version, prompt_template_hash, output_schema_id, model_tier,
  allowed_tools: [...],
  budget: { max_input_tokens, max_output_tokens, max_tool_calls, max_cost_cents, max_wall_seconds },
  inputs: [ { ref, kind, trust: "trusted" | "untrusted" } ],
  idempotency_key: hash(agent_version, inputs, output_schema_id)
}
```

Execution: immutable system policy → task instructions → inputs, with untrusted inputs wrapped as
`<untrusted_content source="…" capture="sha256:…">` → bounded loop of model and tool calls through the gateway → schema
and invariant validation → one repair attempt → completed or `FAILED_NEEDS_HUMAN`. Identical idempotency keys reuse the
stored result. Raw prompts and outputs are stored with restricted access (they may contain personal data).

Prompt-injection controls: untrusted text never enters the instruction sections; agents with untrusted input cannot reach
`X-EXT`, other leads' data or secrets; URLs in outputs must come from already fetched evidence; the sanitizer removes
scripts, hidden elements and comments and flags instruction-like text (flagging is not relied on for safety); repeated
policy denials end the task with a `policy.violation` event.

## 6. Evaluation (thresholds P-29, HYPOTHESIS)

| Agent | Eval set | Initial pass criteria |
|---|---|---|
| A2 | Labelled listings (synthetic + reviewed) | High category accuracy; "ambiguous" preferred to wrong guesses |
| A3 | Diagnoses | 0 statements without finding refs; impact always worded as hypothesis |
| A4 | Human-labelled businesses + adversarial pages | High claim precision; 0 fabricated snippets; 0 tool misuse under injection |
| A5–A8 | Synthetic and approved real businesses | Schema-valid after ≤ 1 repair; 0 unsupported claims; rubric met |
| A9 | Labelled screenshots | Agreement with the designer on major defects (advisory only) |
| A10 | Sales packages | 100 % mandatory notices; 0 prices outside the table; 0 undated claims |
| A11 | Labelled replies | Opt-out recall 100 % (doubt → human) |

## 7. Human-in-the-loop points

| Point | Phase | Notes |
|---|---|---|
| Shortlist approval | M1 | `REVIEW_PRIORITY` → `SHORTLISTED` only with an approval for the exact action |
| Budget change | M1 | Explicit new number |
| Review queue | M1+ | Ambiguous identity, conflicting evidence affecting a gate, failures |
| Campaign plan | M2b+ | Sites/sources, quotas, budget |
| Preview (T1/T2) | M7 | Gated; T2 rule PENDING (PD-21) |
| Contact | P1, M8 | Gated; exact text and channel |
| Publication | M9 | Client sign-off + approval |
| Data source / external destination | later | Terms review attached |

## 8. How agent actions are recorded

The runner and the gateway write the events — model calls (token counts, prompt hash, cost), tool calls (inputs hash,
outcome, cost), validation results, repairs, denials. The agent's own description of what it did is stored, if at all,
as output content, never as the record of the action. Each event has actor, cause, input hash, output reference, cost and
outcome ([data-contracts § 7](data-contracts.md#7-event)), so the future dashboard can show what each agent actually did.
