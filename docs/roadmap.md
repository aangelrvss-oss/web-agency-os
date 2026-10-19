# Web Agency OS — Roadmap

Revision: Phase 0, corrected after the Phase 0 review ([phase0-review.md](phase0-review.md)). Date: 2026-10-19.
Status: **proposal.** No phase starts without the user's explicit approval. Each phase ends with a short report (what was
built, test results, costs incurred, open risks) and a decision to continue. Values `P-xx` are provisional parameters
(HYPOTHESIS) listed in [decisions.md](decisions.md#provisional-parameters).

## 0. Overview

| Phase | Theme | AI? | Paid APIs? | Real third-party sites? | Outward-facing? | Status |
|---|---|---|---|---|---|---|
| M0 | Phase 0 design + review + correction | No | No | No | No | Done (pending user review of this correction) |
| **M1** | Minimal deterministic core (offline, synthetic) | No | No | No | No | **Specified; implementation not authorized (PD-01)** |
| M2a | Diagnosis engine on local fixture sites | No | No | No (loopback only) | No | Requires PD-08–PD-10 |
| M2b | Controlled real-site diagnosis pilot | No | No | **Yes — gated** | No | Gated (§2) |
| P1 | Business validation pilot (manual first) | No | No | Yes (from M2b) | **Yes — gated** | Gated (§2) |
| M3 | Observability dashboard | No | No | No | No | Deferred (D-004) |
| M4 | Discovery and scoring on approved sources | Optional | Source-dependent | Yes — gated | No | Gated |
| M5 | Agent runtime and first agents | **Yes** | **First LLM spend** | Same-site reads — gated | No | Gated |
| M6a | Reference website built by hand | No | No | No | No | Requires PD-25 |
| M6b | Factory automation on synthetic businesses | Yes | LLM | No | No | Gated |
| M7 | Concepts and previews for real leads | Yes | LLM | Yes | Private previews — gated | Gated |
| M8 | Sales preparation and lawful contact | Yes | LLM | No | **Yes — gated** | Gated |
| M9 | Delivery and publication | Yes | Hosting | — | **Yes — gated** | Gated |
| S1 | AgentScope evaluation | — | — | — | — | Excluded this phase (D-005) |

## 1. Current position

Phase 0 documentation has been corrected to incorporate the review and the user's decisions D-018 to D-021. The next
step is the user's review of this correction. M1 implementation starts only after explicit authorization and after the
decisions blocking M1 (PD-01 to PD-07) are taken.

## 2. Gated activities and their entry requirements

These activities are **out of scope** until the listed requirements are met and the user approves the phase (D-020).

| Activity | Entry requirements (all) |
|---|---|
| Crawling or measuring real websites (M2b and later) | M1 and M2a accepted; sandboxed browser environment approved (PD-08); agency identity, website and opt-out contact for the User-Agent (PD-11, fixes E5); documented legal basis for analysing business sites including sole traders', reviewed by counsel (PD-13, fixes E4); capture retention policy (PD-14); approved site list and its source (PD-15); a CLI-recorded campaign approval |
| Any commercial contact (P1, M8) | Written legal review of channels and notices (PD-22); agency legal identity (PD-11); legitimate-interest assessment; exclusion-list procedure; suppression working; pilot success criteria set (PD-16); per-contact approval |
| Automatic preview generation (M6b on real leads, M7) | M6a reference site accepted; design reviewer and rubric (PD-25); asset provenance policy enforced; counsel's view on using prospect names/logos in private previews; preview delivery decided (PD-19); T2 rule decided (PD-21); LLM provider and cap (PD-18) |
| Any public deployment (previews or sites) | Production quality profile; legal pages; asset licences verified; client sign-off; hosting decision; `PUBLISH` approval |
| First paid API call | Provider selected; terms and data-processing terms reviewed; prices recorded; user-set cap; provider-side cap; paid-call switch changed by the user in both places |
| Real personal data stored | Legal basis documented; retention periods decided (PD-24, P-22); storage protection (encryption at rest, access control) decided |

## M1 — Minimal deterministic core (offline)

**Decided scope (D-018):** local Python + SQLite program; no AI; no paid APIs; no network connections; synthetic data
only. **Excluded (D-019):** OI code integration, PostgreSQL, dashboard, AgentScope, Google Sheets.

### Goal

Prove the foundations on which everything else depends: evidence that cannot be invented, an assessment that keeps
technical evidence apart from opportunity and intent, guarded state transitions, an append-only event log, approvals
bound to exact actions, a spend switch that cannot be bypassed, and exports that are safe to open.

### Modules

| Module | Responsibility |
|---|---|
| `contracts/` | JSON Schemas for the 8 core contracts ([data-contracts § 0](data-contracts.md#0-which-contracts-belong-to-m1)) + validator (library choice PD-02) |
| `store` | SQLite schema, migrations, append-only triggers, integrity check at startup ([architecture § 6](architecture.md#6-m1-storage-sqlite-triggers-and-the-event-log--design-and-limitations)) |
| `evidence` | Invariants and `evidence_strength` rules |
| `assessment` | Three-layer scoring from `scoring.v1.json` and `impact_rules.v1.json`, with `rules_hash` |
| `workflow` | Transition table ([architecture § 5.4](architecture.md#54-lead-state-machine)), guards, optimistic version check |
| `approvals` | Requests, decisions and executions bound to `action_sha256` |
| `budget` | Paid-call switch (code constant + configuration, both off), price table, ledger |
| `gateway` | Only module that invokes tools; M1 tools are fakes; denials are ledger rows and events |
| `privacy` | Suppression, erasure and retention commands; checks that events carry no personal values |
| `export` | Safe CSV ([data-contracts § 11](data-contracts.md#11-csv-export-format-m1)) |
| `cli` | `init`, `import`, `evidence add`, `score`, `transition`, `approve request/decide/list`, `budget show/request-change`, `suppress`, `erase`, `retention run`, `export csv`, `trace`, `verify` |

### Fixtures

Synthetic only: one campaign with synthetic value bands; about a dozen synthetic leads covering every bucket, every gate
outcome, contraindications, conflicts and suppression; synthetic capture texts; synthetic sole-trader names, phones and
emails (`.example` domains, reserved test numbers) used to test privacy rules.

### Acceptance tests

The five tests from the review (AT1.1–AT1.5) plus seven added tests (AT1.6–AT1.12). All tests run with network access
blocked.

| ID | Test | Pass condition |
|---|---|---|
| **AT1.1** | **Evidence is not invented** | A `KNOWN` record whose snippet is not a literal substring of its capture text is rejected (`evidence.rejected`, reason recorded) and not stored as `KNOWN`. A `KNOWN` record without `source_url` fails schema validation. A `KNOWN` phone or email not literally present in its snippet is rejected. Two incompatible `KNOWN` values for one field resolve to `CONFLICTING`. |
| **AT1.2** | **Guarded transitions** | `DISCOVERED → SHORTLISTED` is rejected; state and version are unchanged; `state.transition_denied` is recorded with the reason. The valid path `DISCOVERED → IDENTITY_RESOLVED → DIAGNOSED → SCORED → SHORTLISTED` (with a valid approval) emits exactly one `state.transitioned` per step. |
| **AT1.3** | **Unknown never passes; determinism** | A lead with `G_GEO = UNKNOWN` gets bucket `PENDING`, never `REVIEW_PRIORITY`. The same inputs twice give identical score records (excluding id and timestamp) and the same `rules_hash`; editing a rules file changes `rules_hash`. |
| **AT1.4** | **Zero spend, zero network** | With the switch off, calling a fake tool with a price > 0 or an unknown price is denied: ledger row `DENIED` with reason, plus `tool.call_denied`. A test asserts that the shipped code constant and configuration are both off. The whole suite runs under a socket/DNS lock; any attempt fails the run. |
| **AT1.5** | **Append-only, traceable log** | `UPDATE` and `DELETE` on `events` fail. `trace <lead>` lists every event of the lead in order, including rejected attempts. If a trigger is missing, the startup integrity check refuses to run. |
| **AT1.6** | **Invalid transitions rejected (exhaustive)** | For every pair of states not in the transition table, the transition is rejected with state and version unchanged and a denial event. Terminal states (`DISQUALIFIED`, `SUPPRESSED`) have no outgoing transition. Unknown state names are rejected. Guard failures are rejected (e.g. `SCORED → SHORTLISTED` with bucket `WATCH`, or with `REVIEW_PRIORITY` but no approval). Of two attempts with the same `state_version`, only the first succeeds. |
| **AT1.7** | **Approval bound to the exact action hash** | An approved `SHORTLIST` action executes once; a second execution is rejected. Changing any field of the action (lead id, parameters) gives a different hash and is rejected. An expired approval (clock moved past `expires_at`) is rejected. A decision by a `SYSTEM` or `AGENT` actor is rejected. A rejected approval cannot be executed. A `BUDGET_CHANGE` approval cannot authorize a `SHORTLIST` action. The same action with keys reordered gives the same hash (canonical JSON). |
| **AT1.8** | **Data protection (synthetic personal data)** | (a) Importing a record with `data_mode = REAL` is rejected, and the rejection event carries no values. (b) After a full scenario, a scan of all event payloads finds none of the fixture personal values (names, phones, emails). (c) Suppressing a lead moves it to `SUPPRESSED`, rejects further transitions, erases its personal values, and causes a re-import of the same identifiers to be rejected. (d) Erasure nulls values and snippets, sets `erased = true` and keeps ids and hashes; `evidence.erased` carries no values. (e) With the clock past `retention_until`, the retention command purges personal values and records `retention.purged`. Retention durations come from configuration (P-22, HYPOTHESIS); tests use synthetic durations. |
| **AT1.9** | **Export safety** | Cells beginning with `=`, `+`, `-`, `@`, tab, CR, LF or their full-width forms are prefixed with `'`. Reading the file back with a standard CSV reader returns exactly the escaped text, including fields with commas, quotes and newlines. Suppressed or erased leads have blank contact columns. The header uses `priority_for_review` and the `purchase_intent` column is `UNKNOWN`. `export.created` records the file's SHA-256 and row count (no values), and they match the file. Exporting a `REAL` record is refused. |
| **AT1.10** | **Technical score ≠ purchase intent** | A lead with `TG = 3` whose findings only have `LOW` impact never reaches `REVIEW_PRIORITY`. A lead with `HIGH` impact but an `UNKNOWN` value band does not reach `REVIEW_PRIORITY`. A `KNOWN` contraindication caps the bucket at `WATCH`. No command changes `purchase_intent` from `UNKNOWN` (also enforced by the schema). A `REVIEW_PRIORITY` lead stays `SCORED` until a human `SHORTLIST` approval is executed. |
| **AT1.11** | **Budget rules** | Tested with injected configuration, never with the shipped configuration. With no budget, any metered call returns `BUDGET_REQUIRED`. A reservation exceeding the per-run or global cap is denied, not truncated. Settlement releases the unused reservation. Changing a cap requires an executed `BUDGET_CHANGE` approval. Ledger totals match the sum of entries. |
| **AT1.12** | **Contract and storage integrity** | Every core contract has at least 3 valid and 3 invalid fixtures. Foreign keys are enforced. CHECK constraints reject invalid enumeration values at the database level. Triggers are present after every migration. |

### Stop conditions

- Any test needs a network connection or real data → stop and redesign the test.
- The three-layer separation cannot be expressed without letting technical severity promote a lead → stop and revise
  the assessment rules before continuing.

### Dependencies and cost

Dependencies: Python standard library; test and schema libraries PENDING (PD-02). External cost: €0.

### Definition of done

All twelve acceptance tests pass offline; the M1 README states the SQLite and event-log limitations
([architecture § 6.3](architecture.md#63-limitations-to-be-stated-in-the-m1-readme-when-implemented)); no network code
path exists; only synthetic data is present in the repository.

## M2a — Diagnosis engine on local fixture sites

**Requires:** M1 accepted; PD-08 (sandbox and admission review of Playwright, Lighthouse, axe-core), PD-09 (catalogue
and impact table), PD-10 (fixture corpus owner). **Network:** loopback only — fixture sites are served locally.

Scope: fetcher with SSRF guard, robots handling, rate limiting; sanitizer; site auditor (Lighthouse via Node API, axe-core,
HTML checks); deterministic basic-fact extractor (fixes E2); local corpus of fixture sites with labelled defects and
adversarial pages.

Acceptance tests (thresholds P-15, P-31 are HYPOTHESIS): detector precision/recall on the corpus; repeated runs give the
same findings and Lighthouse spread is recorded; the SSRF suite (private, loopback-other-than-test-server, link-local,
metadata ranges, IPv4/IPv6, DNS rebinding, redirect chains) is blocked; robots disallow is respected; adversarial pages
do not change deterministic outputs; extracted facts match corpus labels; no request leaves the machine.

Note: a synthetic corpus mainly tests the code; it says little about real websites.

## M2b — Controlled real-site diagnosis pilot (gated)

**Requires:** everything in §2 for real-site crawling. Scope: passive diagnosis of a small, approved list of real sites
(size set at approval).

Acceptance (thresholds P-16 are HYPOTHESIS):

1. A human reviewer gives each site **two separate labels**: "are the findings correct?" and "would you propose a new
   website? yes / no / unsure, and why".
2. Base rates of each finding are reported; findings present on almost every site are flagged as weakly discriminating
   (H-7).
3. Fetch logs show only GET/HEAD of linked pages within P-10 and P-11.

Stop if: any non-passive request is observed; or reviewer agreement on findings is below the agreed level.

## P1 — Business validation pilot (manual first, gated)

**Purpose:** test hypotheses H-2 and H-3 before building generation. **Requires:** everything in §2 for commercial
contact.

1. Choose one category and one area (PD-12) and a small number of businesses from a documented, lawful source.
2. Diagnose them (M2b) and apply the two human labels.
3. Select a handful and prepare a one-page diagnosis (T0) by hand or semi-automatically.
4. Contact them only through channels approved by counsel, offering the free report; record outcomes as human
   interactions (the only source of `purchase_intent`).
5. For those who request it (recorded consent), send the report; for very few, prepare a concept (T1) by hand.
6. Measure report requests, meetings, proposals, sales, hours spent, and which findings interested people.

Success criteria are set by the user **before** the pilot (PD-16). With small samples the results are directional, not
statistical. Generation phases (M6b, M7) are reconsidered only after P1.

## M3 — Observability dashboard (deferred)

Projection of the event log: pipeline, activity per worker/agent, sources, outputs, costs, errors, approval queue,
authentication and roles. No simulated activity. Acceptance thresholds (P-30) are HYPOTHESIS. PostgreSQL is considered
here if concurrent access requires it.

## M4 — Discovery and scoring on approved sources (gated)

Requires approved sources (terms/licence review), category value bands (PD-17), legal basis and DPIA decision (PD-24),
retention periods (P-22). Acceptance: no false identity merges on labelled data; full rule trace per lead; calibration
against human labels (P-17, HYPOTHESIS) before any generation.

## M5 — Agent runtime and first agents (gated; first paid spend)

Requires PD-18 and the §2 requirements for the first paid call. Initial agents: research (A4) and diagnosis narrative
(A3) only. Acceptance: schema validity, zero unsupported claims, literal snippets, zero tool-policy violations on a
prompt-injection suite, measured cost within the user's cap (P-29, HYPOTHESIS).

## M6a — Reference website built by hand

Requires PD-25 (design reviewer and rubric criteria). Build one website by hand for a fictional business of the first
category, at the target quality, and run it through the quality gates. Purpose: set the quality bar, test H-5 and the
provisional targets P-26, verify browser support for scroll-driven animations, and define the conversion components
([quality-gates § 1.3](quality-gates.md#13-conversion-components-required-catalogue)).

## M6b — Factory automation on synthetic businesses (gated)

Extract components and tokens from the reference site; one theme and a small component set first; manifest validation;
deterministic build; QA runner; site-assembler agent. Acceptance: synthetic businesses pass the preview and production
profiles; reproducible build hash; design rubric met; unsafe manifests rejected; reduced-motion run shows no animation.

## M7 — Concepts and previews for real leads (gated)

Requires §2 automatic-preview requirements. Previews private, labelled, expiring; every fact traced to evidence or
shown as a placeholder; quotas (P-24) never exceeded.

## M8 — Sales preparation and lawful contact (gated)

Requires §2 commercial-contact requirements. No send capability in code; drafts include mandatory notices; suppression
blocks every channel; a contact attempt needs an approval for the exact text and channel.

## M9 — Delivery and publication (gated)

Requires §2 public-deployment requirements. Publication only after client sign-off and a `PUBLISH` approval.

## S1 — AgentScope evaluation (excluded this phase)

Only reconsidered once an agent runtime exists. If ever run: sandboxed, mock model, no secrets, egress blocked; pass
criteria include zero built-in tools (no shell/file tools), all model traffic through the WAOS gateway, lossless event
mirroring into the WAOS log, no ownership of state transitions, clean dependency review, and stable upgrades.
Facts about AgentScope in these documents are REPORTED, not verified.

## 3. Global stop conditions

1. A network call outside the gateway, or a gateway call without a policy decision.
2. Spend without a reservation, or a ledger mismatch.
3. Any outward-facing action without a matching approval.
4. Real personal data appearing where only synthetic data is allowed, or personal values found in events.
5. Prompt-injection-induced tool misuse or data crossing between leads (later phases).
6. A legal blocker raised by counsel.
7. A dependency with a new unpatched critical advisory on the execution path.

## 4. Costs

### 4.1 Free initial configuration (M1, M2a)

Local machine or this environment; Python + SQLite; Node.js tools run locally from M2a (Lighthouse locally, not a hosted
API that needs an account); no AI; no hosting; fixtures and, later, operator-prepared CSV lists. External API cost: €0.
Real costs not covered by any API figure: human time (design, review, sales), legal advice, later a domain and hosting.

### 4.2 Spend control (layers, strongest first)

1. **No credentials exist** in the environment — the strongest control.
2. **Double switch:** code constant + configuration; both must be changed by the user.
3. **Single egress** through the gateway; network locked in tests.
4. **Unknown price = blocked**; prices only from `pricing.v1.json`.
5. **Reserve before call**; deny when a cap would be exceeded.
6. **Provider-side cap**: prepaid credit without automatic top-up (when a provider exists).
7. **Reconciliation** with provider usage; mismatch halts the provider.
8. **Kill switch**, and an approval for any cap change.

M1 implements and tests layers 1–5 and the approval for cap changes.

### 4.3 Cost model (symbolic until providers and volumes exist)

`cost(stage) = Σ calls × unit_price + tokens_in × p_in + tokens_out × p_out + compute_minutes × p_compute`.
Volumes and conversion rates are not set (P-33); token envelopes are HYPOTHESIS (P-25). No euro figures are given.

## 5. Next step

1. The user reviews this corrected documentation.
2. The user takes the decisions blocking M1 (PD-01 to PD-07 in [decisions.md](decisions.md#blocking-m1-implementation)).
3. Only then, with explicit authorization, M1 is implemented as specified above.

In parallel and outside the system, starting the legal consultation is recommended because it has the longest lead time
and gates M2b, P1 and every contact phase.
