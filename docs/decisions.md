# Web Agency OS — Decisions, Assumptions and Unknowns (Phase 0)

Date: 2026-10-19. Format: short ADRs. Status values: **Proposed** (needs user confirmation), **Accepted** (constraint
given by the user or required by law/safety), **Deferred**.

## Decisions

### D-001 — Independent repository; contract-level integration with OI
**Status:** Proposed. **Context:** OI is a working, carefully constrained Python engine on an unmerged branch
(`claude/zealous-archimedes-qb70kr`, head `19aeeb8`); its `main` holds only a README. **Decision:** WAOS is a separate
codebase. It adopts OI's vocabularies and rule designs and exchanges `evidence_input.v1` / `opportunity_record.v1`
documents through an OI bridge, with OI schemas vendored and hash-pinned by commit SHA. No imports of `oi.*`, no shared
database. **Consequences:** duplication of a few small rule evaluators; freedom to evolve both; OI changes (e.g.
vocabulary convergence) are separate, explicitly approved OI tasks.

### D-002 — Deterministic control plane; agents only propose
**Status:** Accepted (user constraint). Workflow transitions, budget, authorization, eligibility, scoring and QA pass/fail
are code. See [agent-design § 1](agent-design.md#1-design-rules).

### D-003 — Adopt OI truth vocabulary and evidence invariants
**Status:** Proposed. `claim_status`, `source_class` (+ `MEASUREMENT`, `PUBLIC_REGISTRY`, `HUMAN_REVIEW`), derived
`evidence_strength`, "UNKNOWN ≠ PASS", literal snippets for `KNOWN`, no pattern-built contact data.

### D-004 — Event store is the source of truth for the dashboard
**Status:** Proposed. The UI is a projection of append-only events; no simulated activity. Optional OpenTelemetry export
for external viewers (GenAI semantic conventions are still in *Development* status — medium confidence — so they are
not a hard dependency).

### D-005 — Do not adopt AgentScope now; run an isolated spike
**Status:** Proposed. **Facts (checked 2026-10-19):** AgentScope 2.0 exists (2.0.0 on 2026-05-25; latest 2.0.10 on
2026-10-12; Apache-2.0; Python ≥ 3.11; releases every 2–3 weeks); 2.0 is not source-compatible with 1.x; versions ≤ 1.0.18
carry four 2026 advisories (code injection in shell/Python tools, three SSRFs — e.g. GHSA-cr24-fv3h-8cjm); 2.0 ships
built-in `Bash`/`Edit`/`Write`/`Read`/`Glob`/`Grep` tools behind a permission system; the standalone AgentScope Studio
repository is **archived** (2.0 ships its own Web UI and an Agent Service with SSE); core dependencies include several
model SDKs, `mcp`, `python-socketio`, `tree_sitter_bash` and OpenTelemetry exporters (medium footprint).
**Decision:** WAOS's requirements (deterministic transitions, budget reservations at a gateway, no shell/filesystem tools,
our own event log) leave the framework mainly as an agent loop and a viewer. Build a thin in-house runner first behind an
`AgentRuntime` interface; evaluate AgentScope 2.0.x in a sandboxed spike with the acceptance tests in
[roadmap § S1](roadmap.md#s1--agentscope-20-spike-optional-parallel-to-m3m5). Never use 1.x. Studio is not planned.

### D-006 — Manifest-driven Astro factory; no agent-written code
**Status:** Proposed. Agents compose typed manifests from a human-built component library; static output; minimal JS.

### D-007 — Tiered generation (T0–T3) with quotas and approval for T2
**Status:** Accepted (user constraint: no full website per lead). See [architecture § 4.2](architecture.md#42-generation-tiers--do-not-build-a-website-for-every-lead).

### D-008 — Previews are private, labelled and expiring
**Status:** Proposed. See [security § 11](security-and-compliance.md#11-previews-and-publication).

### D-009 — No automatic outbound communication; email only with consent
**Status:** Accepted (user constraint + LSSI Art. 21). The system has no send capability; a human sends after approval.
Email/electronic messages require a consent record or prior contract.

### D-010 — Python control plane, Node.js build/QA worker
**Status:** Proposed. Python matches OI and the team's existing code; the web toolchain (Astro, Playwright, Lighthouse,
axe) is Node-native and runs in a separate sandboxed container.

### D-011 — PostgreSQL for state, events and queue (SQLite for M1 tests)
**Status:** Proposed. `FOR UPDATE SKIP LOCKED` job queue; no message broker or workflow engine (e.g. Temporal) until
scale requires it.

### D-012 — Lighthouse via Node API with median-of-N, not Lighthouse CI
**Status:** Proposed. `@lhci/cli` 0.15.1 (2025-06-25) is stale and bundles Lighthouse 12.6.1 while Lighthouse is at 13.5.0
(2026-09-18). Re-evaluate LHCI if it is updated.

### D-013 — Accessibility target WCAG 2.2 AA; never claim AAA
**Status:** Accepted (user constraint: do not confuse visual quality with AAA). Automated checks are necessary, not sufficient.

### D-014 — Passive diagnosis only; no security findings
**Status:** Proposed. See [security § 6.2](security-and-compliance.md#62-passive-diagnosis-rules-no-security-testing).

### D-015 — Google Places is not a lead-database source
**Status:** Proposed. Places terms forbid caching/storing content other than `place_id` (and lat/lng ≤ 30 days).
Scraping Google Maps is excluded.

### D-016 — Local CSV/XLSX export first; Google Sheets only with a standing scoped approval
**Status:** Proposed; needs user choice.

### D-017 — First paid spend is gated
**Status:** Accepted (user constraint). No paid API before M5 and only after the user sets a monthly cap and selects a provider.

## Dependency assessment

Facts gathered from PyPI/npm registries, GitHub advisories, official docs on 2026-10-19 (GitHub API access was limited;
counts of open issues are approximate). Nothing was installed or executed.

| Candidate | Latest / date | Licence | Runtime | Advisories / maintenance | Verdict |
|---|---|---|---|---|---|
| AgentScope | 2.0.10 / 2026-10-12 | Apache-2.0 | Python ≥ 3.11 | ≤ 1.0.18: 4 advisories (code injection, SSRF); none flagged on ≥ 1.0.19 / 2.0.x (fix versions not stated); 2.0 breaking vs 1.x; Studio archived | **Spike only** (D-005) |
| AgentScope Studio (`@agentscope/studio`) | 1.0.9 / 2026-03-06 | — | Node ≥ 20 | Repository archived | **Rejected** |
| Astro | 7.4.0 / 2026-10-15 | MIT | Node ≥ 22.22.0 | Several 2024–2026 advisories incl. **critical** GHSA-26w7-cxv4-gfx2 (fixed 7.2.8), Host-header SSRF (fixed 6.4.6), XSS fixes (to 7.0.10); very active | **Adopt at M6**, pinned ≥ 7.2.8, static output, restricted image inputs |
| Playwright | 1.64.1 / 2026-10-14 | Apache-2.0 | Node ≥ 20 | CVE-2025-59288 (fixed 1.55.1); monthly releases | **Adopt at M2** |
| Lighthouse | 13.5.0 / 2026-09-18 | Apache-2.0 | Node ≥ 22.19 | No advisories found; monthly releases | **Adopt at M2** (Node API) |
| Lighthouse CI (`@lhci/cli`) | 0.15.1 / 2025-06-25 | Apache-2.0 | Node | No advisories; stale; bundles Lighthouse 12.6.1; transitive deps not audited | **Not adopted** (D-012) |
| axe-core / `@axe-core/playwright` | 4.14.0 / 2026-10-05, 2026-10-15 | MPL-2.0 | Node ≥ 22.12 (playwright pkg) | No advisories | **Adopt at M2** (unmodified) |
| OpenTelemetry GenAI conventions | Development status | Apache-2.0 | — | Not stable (medium confidence) | Optional export only |
| Temporal (or similar) | not assessed | — | — | — | **Deferred**; Postgres queue suffices |

Every adopted item still goes through the full admission policy (transitive tree, install scripts, sandboxed first run)
at the start of its milestone.

## Assumptions

| ID | Assumption | Validated by |
|---|---|---|
| AS-1 | Small local service businesses in the target area often have websites with measurable mobile/performance/contact-path gaps | M2 real-site pilot (≤ 25 sites) |
| AS-2 | A website gap + high-value category correlates with willingness to buy | M4 calibration with human labels; M8 outcomes |
| AS-3 | Phone/postal/in-person first contact offering a free diagnosis can generate consented follow-ups | M8 pilot, after legal review |
| AS-4 | Category value bands (renovation/HVAC/solar `HIGH`, mechanics `MEDIUM`, …) | User confirmation |
| AS-5 | Token envelopes per agent in agent-design §3 | Measured in M5 |
| AS-6 | "Southeast Madrid" ≈ Puente de Vallecas, Villa de Vallecas, Moratalaz, Vicálvaro, Rivas-Vaciamadrid, Arganda del Rey | User confirmation |
| AS-7 | The OI public edition's committed test record (371 run, 0 failures, 15 skipped) reflects its code | Not reproduced in Phase 0 (execution not permitted); re-run in an approved sandbox before relying on OI behaviour |

## Unknowns

| ID | Unknown | Blocks |
|---|---|---|
| U-1 | LLM provider and model mapping; prices | M5 cost estimates |
| U-2 | Discovery sources that pass ToS/licence review | M4 |
| U-3 | Preview hosting (private host vs local screenshots/PDF only) | M7 |
| U-4 | Agency legal identity for notices (LSSI Art. 10, GDPR Art. 13/14) | M8 |
| U-5 | Legal answers in security doc § 13 | M4 (data), M8 (outreach) |
| U-6 | Price list per tier | M8 sales packages |
| U-7 | Content of OI's private copy (pilot data, F12–F15.1) | Only if WAOS needs those learnings in detail |
| U-8 | Whether OI will converge its two `source_class` vocabularies | OI bridge mapping table |

## Decisions needed from the user (prioritized)

1. Confirm the target area and initial categories (AS-4, AS-6).
2. Accept the outreach model change (phone/postal/in-person first; email only after consent) and engage Spanish counsel.
3. Select the LLM provider and a monthly cap for M5.
4. Decide preview delivery (private hosting vs screenshots/PDF).
5. Choose spreadsheet target (local XLSX vs Google Sheets with standing approval).
6. Provide agency legal identity and price ranges per tier.
7. Approve the milestone order in [roadmap.md](roadmap.md).
