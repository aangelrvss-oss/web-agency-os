# Web Agency OS — Implementation Roadmap (Phase 0)

Status: **proposal**. Date: 2026-10-19. No milestone starts without the user's go-ahead; each ends with a short report
(what was built, test results, costs incurred, open risks) and a decision to continue.

## 0. Overview

| Milestone | Theme | Needs LLM? | Needs paid APIs? | Touches real third-party sites? | Outward-facing? |
|---|---|---|---|---|---|
| M0 | Phase 0 architecture (this) | No | No | No | No |
| M1 | Contracts + deterministic control plane (offline) | No | No | No | No |
| M2 | Website diagnosis engine | No | No | Yes, passive, ≤ 25 sites after approval | No |
| M3 | Dashboard on real events | No | No | No | No |
| S1 | AgentScope 2.0 spike (optional) | Mock model only | No | No | No |
| M4 | Discovery, identity, scoring, export | Optional (A1, A2) | Depends on source | Yes | No |
| M5 | Agent runtime + research agent | **Yes (first spend)** | LLM | Yes (same-site reads) | No |
| M6 | Astro factory on synthetic businesses | Yes (A8, A9) | LLM | No | No |
| M7 | Strategy, creative, T1/T2 previews for real leads | Yes | LLM (+ stock, optional) | Yes | No (private previews) |
| M8 | Sales prep, CRM, outreach drafts | Yes | LLM | No | **Yes, human-sent only, after legal review** |
| M9 | Delivery and publication | Yes | Hosting | — | **Yes, after approval** |

## M0 — Phase 0 (this milestone)

- **Deliverables:** `docs/architecture.md`, `agent-design.md`, `data-contracts.md`, `security-and-compliance.md`,
  `quality-gates.md`, `roadmap.md`, `decisions.md`; read-only audit of OI.
- **Acceptance:** documents reviewed by the user; the decisions in [decisions.md § Decisions needed](decisions.md#decisions-needed-from-the-user-prioritized)
  answered or explicitly deferred.
- **Cost:** €0 external.

## M1 — Contracts and deterministic control plane (offline)

- **Scope:** Python package skeleton; JSON Schemas for every contract in [data-contracts](data-contracts.md) with
  validators; lead and project state machines; event store + read-model projector (SQLite in tests); policy engine;
  budget service with reservations; approval service with **no** external-write executors wired; tool gateway with the
  socket lock for tests; OI bridge (vendored, hash-pinned OI schemas); synthetic fixtures; CI with lint, type check,
  tests, OSV scan.
- **Acceptance tests:**
  - AT1.1 Every schema has ≥ 3 valid and ≥ 3 invalid fixtures; evidence invariants (KNOWN needs source + literal
    snippet; contact values literal; NOT_FOUND ⇒ null/UNKNOWN; conflicting KNOWN ⇒ CONFLICTING) are tested.
  - AT1.2 Exhaustive test over all state pairs: only declared transitions succeed; guards are enforced.
  - AT1.3 Budget: no budget ⇒ `BUDGET_REQUIRED`; a reservation exceeding any scope is denied; 50 concurrent reservations
    never overspend; unknown-price tools are blocked in autonomous mode.
  - AT1.4 No agent identity can invoke an `X-EXT` tool; an approved action executes exactly once and only for its
    `exact_action_sha256`.
  - AT1.5 The whole test suite passes with network access blocked; any socket attempt fails the run.
  - AT1.6 Replaying the event log rebuilds an identical read model.
  - AT1.7 Every WAOS `EvidenceRecord` fixture exports to OI `evidence_input.v1` and validates against the vendored OI
    schema; unmappable values are rejected; the vendored-schema hash test fails on drift.
- **Stop conditions:** the OI mapping loses information that affects `KNOWN` status → stop and revise D-003.
- **Dependencies:** Python stdlib, `jsonschema` (MIT), `pytest` (MIT) — subject to admission checks.
- **Cost:** €0 external.

## M2 — Website diagnosis engine (the first-party evidence producer)

- **Scope:** fetcher (SSRF guard, robots, rate limits, identifying UA), sanitizer, site auditor (Lighthouse Node API
  median-of-3, axe, HTML/SEO/contact-path checks), finding catalogue v1, sandbox container images; a local corpus of ≥ 20
  fixture sites with labelled defects plus adversarial pages; then a real-site pilot on ≤ 25 public sites chosen by the
  user, run only after a `CAMPAIGN_PLAN`-type approval.
- **Acceptance tests:**
  - AT2.1 Each detector: precision ≥ 0.95, recall ≥ 0.90 on the corpus.
  - AT2.2 Same fixture twice ⇒ identical findings; Lighthouse spread recorded; thresholds have margin.
  - AT2.3 SSRF suite (private/loopback/link-local/metadata IPv4+IPv6, DNS rebinding, redirect chains) fully blocked.
  - AT2.4 robots.txt disallow respected; rate limits observed in fetch logs.
  - AT2.5 Fetch logs from the pilot show only GET/HEAD to linked pages (no form posts, no probing).
  - AT2.6 Human reviewer agrees with ≥ 90 % of pilot findings.
  - AT2.7 Adversarial pages do not change deterministic outputs; suspicious content is flagged.
- **Stop conditions:** pilot agreement < 90 % → diagnosis not used for scoring until fixed; any non-passive request
  observed → stop and fix before further real fetches.
- **Dependencies:** Playwright 1.64.x, Lighthouse 13.x, axe-core 4.14 (+ `@axe-core/playwright`), HTML validator (to assess).
- **Cost:** €0 external (local compute). Compute estimate: ~3 Lighthouse runs × 20–40 s per site ⇒ ~1–2 CPU-minutes per site.

## M3 — Dashboard on real events

- **Scope:** read-model API, SSE stream, views from [architecture § 9.2](architecture.md#92-views), authentication,
  roles, approval actions, CSRF protection, sandboxed preview origin.
- **Acceptance tests:** AT3.1 the UI renders only persisted events (no client-side fabricated states); AT3.2 event-to-UI
  lag ≤ 2 s at 50 events/s; AT3.3 approvals require an authenticated approver and are logged; AT3.4 CSRF and stored-XSS
  tests with malicious captured content pass; AT3.5 RBAC: viewers cannot see raw prompts/captures.
- **Stop conditions:** any XSS from captured content → stop.
- **Cost:** €0 external (hosting decision deferred; runs locally).

## S1 — AgentScope 2.0 spike (optional, parallel to M3–M5)

Goal: decide whether AgentScope 2.0.x replaces the in-house runner behind the `AgentRuntime` interface (D-005).
Precondition: static review of its pinned dependency tree done (licences, advisories, install scripts). Runs in a
disposable container with no secrets and egress blocked; uses a **mock model** (no paid calls).

| Test | Pass criterion |
|---|---|
| S1.1 Zero built-in tools | Agents can be built with none of `Bash/Edit/Write/Read/Glob/Grep` registered; an injected request to use them fails closed |
| S1.2 Gateway-only model access | All model calls go through our gateway wrapper (budget reservations apply); with egress blocked, nothing else tries to connect |
| S1.3 Event coverage | Every model call, tool call and agent step can be mirrored into our event store (hooks/middleware/OTel) with ≤ 1 s delay and no loss across a crash |
| S1.4 No hidden side effects | No telemetry, file writes outside scratch, or network calls at import/run time |
| S1.5 Schema-validated outputs | Structured output with our JSON Schemas and repair loop works without framework-specific coupling |
| S1.6 Upgrade risk | Pinned 2.0.x; two consecutive patch upgrades pass the suite unchanged |
| S1.7 Value | Measurably less code than the in-house runner for the same tests, with no weaker control |

Adopt only if all pass. Otherwise keep the in-house runner; record the outcome as an ADR.

## M4 — Discovery, identity, scoring, export

- **Preconditions:** discovery sources selected and each approved via `DATA_SOURCE_ENABLE` with ToS/licence review;
  LIA written; DPIA screening done; target area and categories confirmed.
- **Scope:** collectors for approved sources (official/open data, OI import, operator CSV), identity resolution,
  `business_classifier` (optional; if used, it triggers the M5 provider decision early), scoring rules v1, local
  CSV/XLSX export with formula-injection protection, retention jobs.
- **Acceptance tests:** AT4.1 dedupe/identity on labelled fixtures (no false merges); AT4.2 scoring deterministic with a
  full rule trace per lead; AT4.3 formula-injection fixtures neutralized; AT4.4 human calibration on 50 real leads:
  reviewer agrees with `PRIORITY` membership ≥ 70 % (initial threshold) before any T1/T2 spend; AT4.5 retention job
  deletes expired personal fields and emits events.
- **Stop conditions:** no source passes review → operator CSV import only; calibration < 70 % → revise scoring before M7.
- **Cost:** source-dependent (TBD); free official sources €0.

## M5 — Agent runtime and research agent (first paid spend)

- **Preconditions:** LLM provider chosen, DPA reviewed, `pricing.v1.json` filled, monthly cap set by the user.
- **Scope:** agent runner (or AgentScope if S1 passed), prompt templates, A3 and A4, eval suites (§6 of agent-design),
  prompt-injection suite (≥ 50 pages).
- **Acceptance tests:** AT5.1 ≥ 98 % schema-valid outputs after ≤ 1 repair; AT5.2 0 unsupported claims on 30 researched
  leads; AT5.3 100 % of `KNOWN` snippets found literally in captures; AT5.4 0 tool-policy violations / scope escapes on the
  injection suite; AT5.5 measured cost per researched lead recorded and within the approved envelope.
- **Stop conditions:** any injection-induced tool misuse → stop and redesign; ledger vs provider usage mismatch → halt
  provider.
- **Cost:** see §2 template.

## M6 — Astro website factory (synthetic businesses)

- **Scope:** tokens, ~25 section components with prop schemas, 3 themes, motion presets, 3 category starters, manifest
  validator, builder, QA runner, A8 and A9.
- **Acceptance tests:** AT6.1 3 synthetic businesses × 3 themes pass the preview **and** production profiles in
  [quality-gates](quality-gates.md); AT6.2 reproducible build hash; AT6.3 designer rubric ≥ 4/5 average; AT6.4 a manifest
  containing scripts/raw HTML/external URLs is rejected; AT6.5 reduced-motion run shows no animation.
- **Stop conditions:** design rubric not met after 2 iterations → a human designer reworks the component library before
  any real preview.
- **Cost:** LLM for A8/A9 evals (template §2); stock imagery optional.

## M7 — Strategy, creative and previews for real shortlisted leads

- **Preconditions:** preview delivery decided (private hosting or screenshots/PDF only); asset policy enforced; counsel
  view on using prospect names/logos in private previews (security § 13 Q4).
- **Scope:** A5, A6, A7; T1 concept cards; T2 previews behind `PREVIEW_T2` approval and quotas.
- **Acceptance tests:** AT7.1 100 % of factual content traced to evidence or rendered as placeholder; AT7.2 no asset
  without `AssetRecord`; no `PREVIEW_ONLY` asset outside previews; AT7.3 quotas never exceeded (test + ledger audit);
  AT7.4 cost per T1/T2 measured; AT7.5 previews non-indexable, access-controlled, expiring, with disclaimer.
- **Stop conditions:** counsel objects to preview use of business identity → switch to anonymized concepts.

## M8 — Sales preparation, CRM and outreach drafts

- **Preconditions:** written legal review of channels (security § 13); agency legal identity and notices; price ranges.
- **Scope:** A10, CRM module, suppression service, consent records, contact-eligibility policy, approval-gated
  human-sent outreach, outcome logging.
- **Acceptance tests:** AT8.1 every draft contains the mandatory notices for its channel; AT8.2 email drafts impossible
  without a consent record; AT8.3 suppression blocks every channel (cross-channel test); AT8.4 Robinson-check timestamp
  required before phone/postal outreach approval; AT8.5 no send capability exists in code (static test + review).
- **Stop conditions:** counsel finds a channel non-viable → channel disabled in policy; any communication without
  approval detected → global stop.
- **Cost:** LLM (template §2) + legal fees (TBD, real cost).

## M9 — Delivery and publication (post-sale)

- **Scope:** project state machine, content collection, change requests (A12), production QA profile, publication via
  `PUBLISH` approval, handover pack (credentials transfer, licences, maintenance terms).
- **Acceptance tests:** AT9.1 publication impossible without client sign-off + approval; AT9.2 production profile passes;
  AT9.3 legal pages present; AT9.4 all assets `PRODUCTION_ALLOWED`.

## 1. Global stop conditions (any milestone)

1. An external network call not made through the gateway, or a gateway call without a policy decision.
2. Spend without a reservation, or ledger/provider mismatch beyond tolerance.
3. Any outward-facing action (message, call log without approval, publication, external write) without a matching approval.
4. Prompt-injection-induced tool misuse or data crossing between leads.
5. Personal data found in logs, prompts or exports beyond policy.
6. A legal blocker raised by counsel.
7. A dependency with a new unpatched critical advisory on the execution path.

On a stop: kill switch, incident note, root cause, ADR, user decision to resume.

## 2. Cost model (to be populated once providers are selected)

Per stage: `cost = Σ_calls(unit_price) + tokens_in × p_in + tokens_out × p_out + compute_minutes × p_compute`.
Prices come from `pricing.v1.json` (versioned, with source and date). All € values below are **TBD**.

Illustrative monthly funnel (ASSUMPTION, to be replaced by measured conversion): 1,000 discovered → 700 identity-resolved
and diagnosed → 140 shortlisted and researched → 40 T1 concepts → 10 T2 previews → sales packages for consented prospects.

| Stage | Units / month | Tokens per unit (in / out, ASSUMPTION) | Other drivers | Unit cost | Monthly cost |
|---|---|---|---|---|---|
| Discovery + classification (A1, A2) | 1,000 | 2k / 0.3k | source fees TBD | TBD | TBD |
| Diagnosis (deterministic) | 700 | — | ~1–2 CPU-min per site | TBD | TBD |
| Diagnosis narrative (A3) | 140 | 4k / 1k | — | TBD | TBD |
| Research (A4) | 140 | 25k / 3k | ≤ 10 fetches | TBD | TBD |
| Strategy + copy + art direction (A5–A7) | 40 | 23k / 7k | stock images TBD | TBD | TBD |
| T1 concept build + QA | 40 | — | build + QA ~5 CPU-min | TBD | TBD |
| T2 assembly + QA review (A8, A9) | 10 | 16k / 7k + 4 images | build + QA ~10 CPU-min, ≤ 2 retries | TBD | TBD |
| Sales package (A10) | ≤ 40 | 8k / 3k | — | TBD | TBD |
| Evals and regression runs | per release | measured in M5 | — | TBD | TBD |
| Infrastructure (DB, workers, preview hosting) | monthly | — | TBD | TBD | TBD |
| Legal review (one-off + periodic) | — | — | counsel | TBD | TBD |

KPIs to measure from M5: cost per diagnosed lead, cost per researched lead, cost per T2 preview, cost per consented
prospect, cost per won client.

## 3. Phase 0 recommendation

**Build first (no LLM, no paid API, low risk, highest leverage):**

1. **M1 — contracts and deterministic control plane**, offline with synthetic fixtures: schemas, state machines, budget
   reservations, approval service without executors, gateway with network lock, OI bridge. Everything else depends on it.
2. **M2 — website diagnosis engine.** It is the core of the value proposition (objectively verifiable problems), it is
   exactly the first-party evidence producer that OI's pilots identified as the bottleneck, and it needs only free
   tooling. Quality is measurable against a labelled corpus before any real site is touched.
3. **M3 — dashboard** over the real event log, so every later agent is observable from day one.

**Defer:**

- AgentScope adoption (spike S1 only; never 1.x; Studio is archived).
- All LLM agents until M5, and image generation indefinitely (licensed library first).
- Google Sheets sync, external CRM integrations, automated reply handling, any automated sending.
- T3 full-site generation until a client has signed; multi-tenant features; Temporal or other workflow engines.
- Paid discovery or data-broker sources.

**Dependencies justified now (subject to the admission checks at each milestone):**

- M1: Python standard library, `jsonschema`, `pytest`.
- M2: Playwright 1.64.x, Lighthouse 13.x (Node API), axe-core 4.14 + `@axe-core/playwright`.
- M3: PostgreSQL; a minimal web framework (to be chosen under the admission policy).
- M6: Astro ≥ 7.2.8 (latest 7.4.x), with restricted image inputs.

**Not justified yet:** AgentScope (pending S1), Lighthouse CI (stale), Temporal, vector databases, general-purpose agent
frameworks, any paid API.

**Must be tested before integrating any framework** (AgentScope or other):

1. It can run with zero built-in tools and cannot execute shell, filesystem or code tools even if prompted.
2. All model and tool traffic passes through the WAOS gateway (budget reservation, policy, logging); nothing else egresses.
3. Its events can be mirrored losslessly into the WAOS event store; its UI is never the system of record.
4. It never owns workflow state transitions.
5. Its pinned dependency tree passes licence, advisory and install-script review, and its first run in a sandbox shows
   no unexpected network or file activity.
6. Upgrades within the pinned major version do not break the acceptance suite.

**Business-model note for the user:** because of LSSI Art. 21, cold email to Spanish businesses is not an option. The
pipeline above is designed for first contact by phone, post or in person offering a free diagnosis, with previews and
email follow-up reserved for prospects who ask for them. Confirming this with Spanish counsel is a precondition of M8 and
should start early because it can change what is worth building in M7.
