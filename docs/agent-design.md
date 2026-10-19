# Web Agency OS — Agent Design (Phase 0)

Status: **proposal, not implemented**. Date: 2026-10-19. See [architecture](architecture.md) for components and state
machines, [data-contracts](data-contracts.md) for the schemas named here.

## 1. Design rules

1. **Agents propose, code decides.** An agent's output is a *proposal* validated against a JSON Schema and business
   invariants. Only the workflow engine changes state; only the budget service authorizes spend; only the approval
   service performs external writes.
2. **One bounded task per invocation.** No long-lived autonomous agents and no agent-to-agent free conversation. The
   workflow engine sequences tasks. Each task has a fixed input, an allowed-tool list, a budget envelope and an output schema.
3. **Deterministic first.** Anything measurable (performance, accessibility, HTTPS, colours used on a site, scoring,
   eligibility, prices) is computed by code. LLMs are used for reading, summarizing, classifying, writing and composing.
4. **No shell, no filesystem, no raw network.** These tools do not exist in the tool registry, so no prompt can unlock them.
5. **Untrusted content is data.** Fetched pages, search results, documents and inbound emails are passed to agents inside
   delimited, provenance-labelled blocks. Agents that receive untrusted content have no external-write tool and no secret.
6. **Every claim is anchored.** A factual statement in any agent output must reference an `evidence_id` or a
   `finding_id`; textual evidence must contain a snippet that appears literally in the stored capture (checked in code).
7. **Versioned and evaluated.** Each agent = `name@version` = prompt template hash + output schema version + model tier.
   A new version ships only if its eval suite passes (§6).

## 2. Deterministic services (no LLM)

| Service | Decides |
|---|---|
| Workflow engine | State transitions, retries, quotas, tier entry (§4.2 of architecture) |
| Policy engine | Tool permissions, egress, contact-channel eligibility, approval requirements, retention |
| Budget service | Reservations, settlements, caps, alerts |
| Identity resolver | `KNOWN_MATCH / KNOWN_MISMATCH / AMBIGUOUS / UNKNOWN` (OI 4-state model, no fuzzy auto-merge) |
| Fetcher + Sanitizer | What is fetched (robots, rate, scope) and how content is cleaned and labelled |
| Site auditor | All website measurements and findings (catalogue in [data-contracts § 4](data-contracts.md#4-measurements-and-findings)) |
| Scoring engine | Gates, eligibility, score interval, bucket |
| Astro builder | Rendering a validated manifest into a static site |
| QA runner | Pass/fail on all [quality gates](quality-gates.md) |
| Pricing table | Offer price ranges per tier (agents read, never invent prices) |
| Suppression service | Opt-outs and do-not-contact, checked before every contact-related action |
| CRM module | Pipeline records, outcome logging (human-entered) |
| Exporters | CSV/XLSX generation with formula-injection neutralization |

## 3. LLM agents

Model tiers are abstract (`small`, `medium`, `large`, `vision`); the mapping to a provider's models is configuration,
decided when the provider is selected (UNKNOWN today). Budget envelopes are initial ASSUMPTIONS to be replaced by measured
values in milestone M5.

| # | Agent | Purpose | Input | Output schema | Reads untrusted content? | Model tier | Envelope (in/out tokens, tool calls) | Milestone |
|---|---|---|---|---|---|---|---|---|
| A1 | `discovery_planner` | Turn a campaign brief (area, categories) into search query proposals and Spanish category synonyms for allowlisted sources | `Campaign` | `DiscoveryPlanProposal` | No | small | 4k / 1k, 2 | M4 |
| A2 | `business_classifier` | Map a discovered entity to the internal category taxonomy; always `INFERRED` | listing record (sanitized) | `ClassificationProposal` | **Yes** | small | 2k / 0.3k, 0 | M4 |
| A3 | `diagnosis_narrator` | Explain measured findings in plain Spanish for internal and sales use; cannot add findings | `Finding[]`, `Measurement[]` (structured only) | `DiagnosisNarrative` | Indirect (structured values only) | small | 4k / 1k, 0 | M5 |
| A4 | `business_researcher` | Read the business's own pages and allowlisted public sources; extract claims with literal snippets | lead, capture ids, same-site URLs | `EvidenceProposal[]` + `ResearchDossier` | **Yes** | medium | 25k / 3k, ≤ 10 fetches | M5 |
| A5 | `website_strategist` | Choose scope within the tier, pages, conversion goal, sections, local-SEO themes | dossier, diagnosis, category playbook | `WebsiteStrategy` | Via validated claims only | medium | 8k / 2k, 2 | M7 |
| A6 | `copywriter` | Write Spanish copy per section; facts must cite evidence | strategy, dossier | `CopyDeck` | Via validated claims only | medium | 10k / 4k, 0 | M7 |
| A7 | `art_director` | Pick theme, palette roles, type pair, imagery slots from the licensed library, motion preset | strategy, measured brand colours | `CreativeBrief` | No | medium | 5k / 1k, ≤ 5 library searches | M7 |
| A8 | `site_assembler` | Compose the `WebsiteProjectManifest` from catalogue components with typed props | strategy, copy deck, creative brief, component schemas | `WebsiteProjectManifest` | No | medium | 12k / 6k, ≤ 3 validations | M6–M7 |
| A9 | `qa_reviewer` | **Advisory** visual critique of screenshots + rubric pre-score; cannot pass a failing gate | `QAReport`, screenshots | `VisualReview` | No (own artifacts) | vision | 4 images + 3k / 1k, 0 | M6 |
| A10 | `sales_preparer` | Draft diagnostic summary, proposal outline, call script, postal letter; email draft only when a consent record exists | dossier, diagnosis, strategy, preview refs, pricing, required notices | `SalesPackage` (drafts) | Via validated claims only | medium | 8k / 3k, 2 | M8 |
| A11 | `reply_triage` | Classify inbound replies (interested / not now / opt-out / other) into CRM proposals | inbound message (sanitized) | `ReplyClassification` | **Yes** | small | 3k / 0.3k, 0 | deferred (after M8) |
| A12 | `delivery_assistant` | Turn client change requests into manifest diffs and content checklists | project, request | `ManifestDiffProposal` | **Yes** (client text) | medium | 10k / 4k, 1 | deferred (M9) |

Deliberately **not** agents: scoring, eligibility, compliance decisions, pricing, QA pass/fail, state transitions,
suppression, opt-out handling (a detected opt-out is applied deterministically and conservatively; ambiguity goes to a human).

### 3.1 Per-agent guardrails (beyond the global rules)

| Agent | Specific constraints enforced in code |
|---|---|
| A1 | Queries only against sources whose `enabled=true` in the source registry; output count ≤ campaign quota; human approves the campaign plan before execution. |
| A2 | Output `claim_status` forced to `INFERRED`; category must exist in taxonomy; never sets gates. |
| A3 | Every sentence must reference ≥ 1 `finding_id`; findings with `sales_safe=false` are excluded from sales narrative input. |
| A4 | `web.fetch_same_site` restricted to the lead's registrable domain (+ allowlisted registries), ≤ 10 pages, GET only; each proposed `KNOWN` claim must carry a snippet that is a literal substring of the sanitized capture (else downgraded to `UNKNOWN` and logged); emails/phones accepted only if literally present; no person-level data beyond business contact details published by the business itself; no inferred attributes about individuals. |
| A5 | Page count and section count ≤ tier limits; must list which findings each choice addresses; cannot request features outside the component catalogue. |
| A6 | Claim detector: digits, years, counts, certifications, awards, ratings, guarantees, superlatives ("líder", "nº 1", "el mejor"), prices and testimonials must link to evidence or the block is rejected; testimonials/reviews can never be generated; placeholders must use the `Placeholder` marker. |
| A7 | Fonts only from the approved (OFL/licensed) list; images only from the asset store with `usage_scope` compatible with the tier; palette contrast checked by code (WCAG AA for text roles). |
| A8 | Output validated against per-component JSON Schemas; no raw HTML, no scripts, no external URLs except evidence-backed contact links; rich text limited to a safe Markdown subset rendered by the builder. |
| A9 | Advisory only: its scores are stored but never used as a gate; disagreements with deterministic results are logged for eval. |
| A10 | Must include the mandatory notices for the channel verbatim (from the compliance template store); prices only from the pricing table; claims about the prospect's site must cite measurement date and tool; email drafts are not generated unless the contact point has a valid `ConsentRecord`; nothing is sent. |
| A11/A12 | No tools; outputs are proposals reviewed by a human. |

## 4. Tool permission model

### 4.1 Tool classes

| Class | Meaning | Examples | Who may call |
|---|---|---|---|
| `R-INT` | Read internal, scoped to the task's lead/project | `catalog.components`, `playbook.get`, `capture.get_text`, `qa.get_report` | Agents per matrix |
| `R-WEB` | Fetch public web through the Fetcher (robots, rate limit, SSRF guard, scope rules) | `web.fetch_same_site` | A4 only |
| `P-INT` | Propose internal records (validated before persistence) | `evidence.propose`, `manifest.validate` | Agents per matrix |
| `M-PAID` | Metered external APIs (the LLM itself, stock library, paid data) — budget reservation mandatory | `llm.complete`, `assets.search_stock` | Runner / A7 |
| `C-SBX` | Sandboxed compute | `build.astro`, `qa.run`, `audit.site` | **Workflow engine only**; agents can only *request* a rebuild via their output |
| `X-EXT` | External write / outward-facing | send email, place call, publish site, write Google Sheet, push to external CRM, create accounts | **No agent.** Approval service after a recorded human decision |
| `SYS` | Shell, filesystem, arbitrary HTTP, code execution, package install | — | **Not implemented**; absent from the registry |

### 4.2 Responsibility / permission matrix

✔ allowed · ✖ not available · ◐ restricted variant (see §3.1)

| Agent | R-INT | R-WEB | P-INT | M-PAID | C-SBX | X-EXT | SYS | Human approval of output required? |
|---|---|---|---|---|---|---|---|---|
| A1 discovery_planner | ✔ | ✖ | ✔ | LLM only | ✖ | ✖ | ✖ | **Yes** (campaign plan) |
| A2 business_classifier | ✖ | ✖ | ✔ | LLM only | ✖ | ✖ | ✖ | No (INFERRED only; ambiguous → review queue) |
| A3 diagnosis_narrator | ✔ | ✖ | ✔ | LLM only | ✖ | ✖ | ✖ | Before any external use (part of sales package) |
| A4 business_researcher | ✔ | ◐ same-site | ✔ | LLM only | ✖ | ✖ | ✖ | No for internal use; conflicts/gates → review queue |
| A5 website_strategist | ✔ | ✖ | ✔ | LLM only | ✖ | ✖ | ✖ | Implicitly via T2 preview approval |
| A6 copywriter | ✔ | ✖ | ✔ | LLM only | ✖ | ✖ | ✖ | Via T2 approval; production copy needs client sign-off |
| A7 art_director | ✔ | ✖ | ✔ | LLM + ◐ stock search | ✖ | ✖ | ✖ | Via T2 approval; designer review |
| A8 site_assembler | ✔ | ✖ | ✔ | LLM only | ✖ (requests only) | ✖ | ✖ | Via QA gates + designer review |
| A9 qa_reviewer | ✔ | ✖ | ✔ | LLM (vision) | ✖ | ✖ | ✖ | Advisory only |
| A10 sales_preparer | ✔ | ✖ | ✔ | LLM only | ✖ | ✖ | ✖ | **Yes** (outreach approval, per message/batch) |
| A11 reply_triage | ✖ | ✖ | ✔ | LLM only | ✖ | ✖ | ✖ | Yes for anything except clear opt-out (applied automatically, conservatively) |
| A12 delivery_assistant | ✔ | ✖ | ✔ | LLM only | ✖ | ✖ | ✖ | Yes (client-facing changes) |

### 4.3 Gateway enforcement (per call)

1. Caller identity = `agent@version` bound to `task_id`; the tool must be in the task's allowlist.
2. Arguments validated against the tool's schema; URL arguments additionally checked against scope rules (registrable
   domain of the lead, allowlisted registries), SSRF rules (no private/link-local/loopback/metadata addresses, re-resolve
   at connect time, ≤ 3 redirects re-checked), method = GET/HEAD.
3. Policy check (Policy engine) → `allow | deny(reason) | require_approval`.
4. Budget reservation for metered tools; denial if any cap level would be exceeded.
5. Execute with timeout and size limits; store raw result by hash; return a sanitized, labelled view to the agent.
6. Emit `tool.call_completed` / `tool.call_denied` with input hash, duration, cost, result reference.

## 5. Agent runner contract

```text
TaskEnvelope {
  task_id, run_id, lead_id?, project_id?,
  agent: "business_researcher", agent_version: "1.0.0",
  prompt_template_hash, output_schema_id: "waos.evidence_proposal.v1",
  model_tier: "medium",
  allowed_tools: ["capture.get_text", "web.fetch_same_site", "evidence.propose"],
  budget: { max_input_tokens, max_output_tokens, max_tool_calls, max_cost_eur, max_wall_seconds },
  inputs: [ { ref, kind, trust: "trusted" | "untrusted" } ],
  idempotency_key: hash(agent_version, inputs, output_schema_id)
}
```

Execution: build prompt (immutable system policy → task instructions → inputs, with untrusted inputs wrapped in
`<untrusted_content source="…" capture="sha256:…">` blocks and a standing instruction that such content is data) →
loop (≤ N turns) of model call / tool calls through the gateway → final output → schema + invariant validation → one
repair attempt with the validator's error list → `task.completed` or `FAILED_NEEDS_HUMAN`. Identical idempotency keys
reuse the stored result (no re-spend). Raw prompts/outputs are stored as artifacts with restricted access, because they may
contain personal data.

Prompt-injection specific controls:

- Untrusted text never appears in the system or task-instruction section.
- Agents with untrusted input cannot reach `X-EXT`, cannot read other leads' data, cannot see secrets; their only
  "exfiltration channel" would be their own output, which is schema-validated and reviewed.
- URLs in outputs must come from evidence `source_url`s already fetched; new URLs are dropped.
- The sanitizer removes scripts, styles, hidden elements (`display:none`, `aria-hidden` off-screen text, zero-size text),
  HTML comments and metadata, and records what it removed; text that looks like instructions to an AI is flagged
  (`injection_suspect=true`) for the dashboard, but detection is not relied upon for safety.
- Repeated policy denials from one task trigger task termination and a `policy.violation` event.

## 6. Evaluation (per agent version)

| Agent | Eval set (built in the milestone where the agent ships) | Pass criteria (initial, to be tuned) |
|---|---|---|
| A2 | 200 labelled listings (synthetic + reviewed real) | Category accuracy ≥ 90 %; "ambiguous" used rather than wrong guesses |
| A3 | 30 diagnoses | 0 statements without finding refs; human clarity rating ≥ 4/5 |
| A4 | 30 businesses with human-labelled claims; 50 adversarial pages (prompt injection, hidden text, fake contact data) | Claim precision ≥ 95 %; 0 fabricated snippets; 0 tool misuse / scope escapes under injection |
| A5–A8 | 3 synthetic + 5 real (private) businesses | 100 % schema-valid after ≤ 1 repair; 0 unsupported factual claims; designer rubric ≥ 4/5 |
| A9 | 50 screenshots with human labels | Agreement with designer on major defects ≥ 80 % (advisory only) |
| A10 | 20 sales packages | 100 % mandatory notices present; 0 prices outside table; 0 claims without measurement date |
| A11 | 100 labelled replies | Opt-out recall = 100 % (any doubt → human) |

Eval runs use fixtures and recorded captures; they are the only automated LLM spend before real-lead processing, and they
run under their own budget line.

## 7. Human-in-the-loop points

| Point | Trigger | Approver | Notes |
|---|---|---|---|
| Campaign plan | Before discovery runs | Operator | Sources, queries, quotas, budget |
| Review queue | Ambiguous identity, `CONFLICTING` evidence affecting a gate, failed QA after retries, schema failures | Operator | Not an approval; resolves uncertainty |
| T2 preview | Before building a full one-page preview | Operator | Shows score, evidence, cost reservation |
| Budget raise | Any cap reached | Budget owner | New explicit cap number |
| Outreach | Before any contact attempt (per message or per approved batch with identical template) | Operator (+ second approver if configured) | Shows exact text, channel, eligibility checks, Robinson/suppression results |
| Publication | Before any site or preview becomes publicly reachable | Operator + client sign-off | Production gates must pass |
| Data source enable | Before a new discovery source or external API is used | Admin | ToS/licence review attached |
| External write destination | Before a standing integration (e.g. a specific Google Sheet) | Admin | Scope-limited, revocable |
