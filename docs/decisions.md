# Web Agency OS — Decisions, Parameters, Verification Status and Pending Questions

Revision: Phase 0, corrected after the Phase 0 review ([phase0-review.md](phase0-review.md)). Date: 2026-10-19.

This document is the single register for:

1. [Status labels](#status-labels) used in every document.
2. [Decisions](#decisions) (ADRs).
3. [Verification status](#verification-status) of facts that the documents rely on.
4. [Provisional parameters](#provisional-parameters) — every numeric threshold or duration is a hypothesis until calibrated or decided.
5. [Hypotheses](#hypotheses) and [unknowns](#unknowns).
6. [Pending decisions](#pending-decisions), grouped by the phase they block.
7. [Correction log](#correction-log-e1e10) for the contradictions found in the review.

## Status labels

| Label | Meaning |
|---|---|
| **VERIFIED** | Checked directly in this project session (files read, commits and repository structure inspected). |
| **REPORTED** | Gathered by the Phase 0 research subagent from cited sources (package registries, advisory databases, BOE, AEPD, official docs). **Not independently re-verified.** Must be re-checked before it is relied on. |
| **HYPOTHESIS** | A working assumption or provisional parameter. No empirical or legal basis yet. (Earlier drafts used "ASSUMPTION"; same meaning.) |
| **PENDING** | Unknown or undecided; needs a user decision, a test, or professional (e.g. legal) advice. |
| **Accepted** | Decision status: decided by the user, or a non-negotiable constraint given by the user. |
| **Adopted (review)** | Decision status: recommended in the Phase 0 review and incorporated by the user's instruction to update the documentation. Can be revisited. |
| **Proposed** | Decision status: design proposal not yet confirmed by the user. |
| **Deferred** | Decision status: explicitly postponed; out of scope for the current phase. |

Nothing in these documents is legal advice. Legal statements are at most **REPORTED** and require review by a qualified
Spanish lawyer before they are acted upon.

## Decisions

### D-001 — Independent repository; no code integration with OI
**Status:** Accepted (code integration excluded in this phase by the user, 2026-10-19). WAOS is a separate codebase. It
adopts OI's truth vocabulary and rule *designs* (re-implemented, not imported). The OI bridge (exchange of
`evidence_input.v1` / `opportunity_record.v1` documents) is **Deferred**; when it is built it will pin OI by commit SHA.
No import of `oi.*`, no shared database.

### D-002 — Deterministic control plane; agents only propose
**Status:** Accepted (user constraint). Workflow transitions, budget, authorization, eligibility, scoring and QA pass/fail
are code. M1 contains no agents at all.

### D-003 — Adopt OI truth vocabulary and evidence invariants
**Status:** Adopted (review). `claim_status`, `source_class` (+ `MEASUREMENT`, `PUBLIC_REGISTRY`, `HUMAN_REVIEW`),
derived `evidence_strength`, "UNKNOWN ≠ PASS", literal snippets for `KNOWN`, no pattern-built contact data. The OI rules
were read statically; OI's behaviour was not executed (see [verification status](#verification-status)).

### D-004 — Event log is the source of truth for observability; dashboard deferred
**Status:** Accepted (dashboard excluded in this phase). The future dashboard is a projection of stored events and never
shows simulated activity. In M1, observability is the CLI command `trace`.

### D-005 — AgentScope: not in this phase
**Status:** Deferred (excluded by the user). A sandboxed evaluation (S1 in the roadmap) can only be considered once an
agent runtime exists. Facts about AgentScope in this repository are **REPORTED**, not verified.

### D-006 — Manifest-driven Astro factory; no agent-written code
**Status:** Proposed. Out of scope until the factory phase is approved.

### D-007 — Tiered generation (T0–T3) with explicit approval
**Status:** Accepted (user constraint: no full website per lead). Corrected in the review: tier entry no longer depends on
contact eligibility (E3). Whether T2 additionally requires the prospect's prior request is **PENDING** (PD-21).
All automatic preview generation is out of scope until its phase requirements are approved (D-020).

### D-008 — Previews are private, labelled and expiring
**Status:** Proposed. Out of scope until the preview phase is approved.

### D-009 — No automatic outbound communication
**Status:** Accepted (user constraint). The system has no send capability. Which channels are lawful is **PENDING** legal
review (see [security-and-compliance § 1](security-and-compliance.md#1-legal-position-status-reported-not-legal-advice)).

### D-010 — Python for the control plane
**Status:** Accepted for M1 (user, 2026-10-19). The Node.js build/QA worker for later phases is Proposed.

### D-011 — SQLite for M1; PostgreSQL deferred
**Status:** Accepted (user, 2026-10-19). SQLite limitations are documented in
[architecture § 6](architecture.md#6-m1-storage-sqlite-triggers-and-the-event-log--design-and-limitations).
PostgreSQL is reconsidered only when concurrent writers or a multi-user dashboard are needed.

### D-012 — Lighthouse via its Node API, not Lighthouse CI
**Status:** Proposed (applies from M2a). Based on REPORTED maintenance data for `@lhci/cli`.

### D-013 — Accessibility target WCAG 2.2 AA; never claim AAA
**Status:** Accepted (user constraint).

### D-014 — Passive diagnosis only; no security findings
**Status:** Proposed. Applies whenever real sites are analysed (M2b), which is itself out of scope until approved.

### D-015 — Google Places is not a lead-database source
**Status:** Proposed, based on REPORTED terms of service; re-check the current terms before any use.

### D-016 — No Google Sheets synchronization in this phase
**Status:** Accepted (excluded by the user). M1 exports local CSV only.

### D-017 — No paid spend in this phase
**Status:** Accepted (user). M1 has no paid APIs; the first paid spend requires a provider decision and a user-set cap.

### D-018 — M1 scope
**Status:** Accepted (user, 2026-10-19). M1 is a local Python + SQLite program with no AI, no paid APIs, no network
connections and synthetic data only. Scope: JSON contracts, evidence, deterministic scoring, state machine, event log,
CLI approvals, spend control and safe CSV export. Specification: [roadmap § M1](roadmap.md#m1--minimal-deterministic-core-offline).
**Implementation is not yet authorized** (PD-01).

### D-019 — Excluded from this phase
**Status:** Accepted (user, 2026-10-19). No OI code integration, no PostgreSQL, no dashboard, no AgentScope, no Google
Sheets synchronization.

### D-020 — Gated activities
**Status:** Accepted (user, 2026-10-19). Out of scope until the requirements of their respective phases are approved:
crawling or measuring real websites; any commercial contact; any public deployment; automatic preview generation.
Entry requirements: [roadmap § 2](roadmap.md#2-gated-activities-and-their-entry-requirements).

### D-021 — Technical evidence ≠ acquisition impact ≠ commercial opportunity ≠ purchase intent
**Status:** Accepted (user, 2026-10-19). Three layers are stored and scored separately
([data-contracts § 6](data-contracts.md#6-three-layer-assessment-technical-evidence-acquisition-impact-commercial-opportunity)).
No technical score is ever interpreted as purchase intent: `purchase_intent` is `UNKNOWN` unless a human records an
interaction with the prospect, and no automated component can set it.

### D-022 — Event log, not event sourcing
**Status:** Adopted (review). Append-only `events` table plus ordinary state tables, written in the same transaction.
The state is not rebuilt from events (former acceptance test AT1.6 removed, E9).

### D-023 — Contactability is separate from opportunity scoring
**Status:** Adopted (review; fixes E3). Contact-channel eligibility no longer contributes to the opportunity bucket. It
gates contact only, and contact is out of scope (D-020).

### D-024 — Events never contain personal-data values
**Status:** Adopted (review). Because the event log is append-only, it must hold identifiers and hashes, not personal
data values, so that erasure and retention can be honoured in the state tables without editing history.

### D-025 — Provisional parameters register
**Status:** Accepted (user instruction, 2026-10-19). Every numeric threshold, duration, quota or rubric score is listed
in [provisional parameters](#provisional-parameters) as HYPOTHESIS until calibrated with data or decided by the user or
counsel. No commercial values, empirical thresholds or legal periods are asserted as facts.

### D-026 — Evaluation status is separate from review priority and limited to a declared scope
**Status:** Accepted (user decision, 2026-10-19; implemented in M2a.1). Each diagnosed lead gets
`PROBLEMS_FOUND`, `NO_PROBLEMS_FOUND` or `INSUFFICIENT_EVIDENCE`, derived from stored evidence and findings. A problem
counts only with a KNOWN finding whose evidence is stored, KNOWN and not erased. `NO_PROBLEMS_FOUND` requires every
check in `evaluation_scope` (rules/diagnosis.v1.json; in `static-html-1.0.0` the three checks whose absence static HTML
can establish) to be KNOWN `NOT_DETECTED`; every other check stays listed as unverified, so the status is never a
guarantee of a healthy site; the audit report says that it does not guarantee the overall quality of the site and lists
the other nine checks as unverified.

### D-027 — A detectable contact channel is a possible contact path, not a working one
**Status:** Accepted (user decision, 2026-10-19; implemented in M2a.1). `NO_MOBILE_CONTACT_PATH` is DETECTED only when
the home page has no `tel:`/`mailto:` link, no WhatsApp click-to-chat link with a number (`https://wa.me/<n>`,
`https://api.whatsapp.com/send?phone=<n>`, `whatsapp://send?phone=<n>`), no contact form (site-search forms excluded)
on the home page or a page it links to, and no "contact" link. A channel found makes the check UNKNOWN: nothing says
the number works, the form submits or the business answers. A WhatsApp number is never stored as a contact fact.

## Verification status

| Item | Status | Detail |
|---|---|---|
| OI repository structure, branches and commits (`main` = README only; implementation on `claude/zealous-archimedes-qb70kr` at `19aeeb8`) | VERIFIED | Inspected via a read-only clone |
| OI source, schemas and rules described in [architecture § 2](architecture.md#2-opportunity-intelligence-oi-read-only-audit) | VERIFIED (static reading) | Code was read, **not executed** |
| OI test results (371 run, 0 failures, 15 skipped) | **Not verified** | OI's own committed `tests/LAST_RUN.json`; execution was not permitted |
| OI private copy (601/601 tests, pilot data) | PENDING | Not available; known only from OI's README |
| Dependency versions, licences, release dates, advisories (AgentScope, Astro, Playwright, Lighthouse, Lighthouse CI, axe-core) | REPORTED | From registries and advisory databases via the research subagent; no transitive tree audited; nothing installed or executed |
| Legal statements (LSSI, LGTel, LOPDGDD, GDPR, AI Act, EAA, DSM, Google terms) | REPORTED or PENDING | See the table in [security-and-compliance § 1.1](security-and-compliance.md#11-legal-claims-and-their-verification-status) |
| SQLite feature availability (STRICT tables, JSON functions) in the execution environment | PENDING | To verify when M1 implementation is authorized |
| Browser support for CSS scroll-driven animations | PENDING | To verify before the factory phase |

## Dependency assessment

All facts in this table are **REPORTED** (research subagent, 2026-10-19). Nothing was installed or executed, and no
transitive dependency tree was audited.

| Candidate | Latest / date (REPORTED) | Licence (REPORTED) | Runtime | Advisories / maintenance (REPORTED) | Phase / verdict |
|---|---|---|---|---|---|
| AgentScope | 2.0.10 / 2026-10-12 | Apache-2.0 | Python ≥ 3.11 | ≤ 1.0.18: 4 advisories (code injection, SSRF); fix versions not stated; 2.0 breaking vs 1.x | Excluded this phase (D-005) |
| AgentScope Studio | 1.0.9 / 2026-03-06 | — | Node ≥ 20 | Repository reported archived | Rejected |
| Astro | 7.4.0 / 2026-10-15 | MIT | Node ≥ 22.22.0 | Several advisories incl. critical GHSA-26w7-cxv4-gfx2 (reported fixed in 7.2.8) | Factory phase only, after admission review |
| Playwright | 1.64.1 / 2026-10-14 | Apache-2.0 | Node ≥ 20 | CVE-2025-59288 (reported fixed in 1.55.1) | M2a, after admission review |
| Lighthouse | 13.5.0 / 2026-09-18 | Apache-2.0 | Node ≥ 22.19 | None reported | M2a, after admission review |
| Lighthouse CI | 0.15.1 / 2025-06-25 | Apache-2.0 | Node | None reported; bundles Lighthouse 12.6.1; low activity | Not adopted (D-012) |
| axe-core / @axe-core/playwright | 4.14.0 | MPL-2.0 | Node ≥ 22.12 | None reported | M2a, after admission review |
| `pytest`, `jsonschema` | not assessed | not assessed | Python | not assessed | **PENDING** (PD-02) |
| HTML validator, JSON-LD checker, dashboard framework, PostgreSQL driver | not assessed | — | — | — | Later phases |

## Provisional parameters

All values are **HYPOTHESIS** unless stated. "Basis" says where the number came from; none has been calibrated.
In M1, parameters are configuration values exercised with synthetic data; tests must not depend on their being correct.

| ID | Parameter | Provisional value | Used in | Basis | How it gets settled |
|---|---|---|---|---|---|
| P-01 | Lighthouse runs per diagnosis | 3, median | Diagnosis | Common practice to reduce variance | Measure spread in M2a |
| P-02 | Lighthouse runs for factory QA | preview 3 / production 5 | Factory QA | Same | Factory phase |
| P-03 | `SLOW_MOBILE` threshold | performance < 50 or LCP > 4.0 s (lab) | Finding catalogue | Lighthouse "poor" score band and the "poor" LCP band defined for field data (not re-verified); applying them to lab data is our choice | Pilot base rates and human agreement |
| P-04 | `LAYOUT_SHIFT` threshold | CLS > 0.25 | Finding catalogue | Same as P-03 | Same |
| P-05 | `BROKEN_INTERNAL_LINKS` | ≥ 3 internal 4xx | Finding catalogue | None | Pilot |
| P-06 | `STALE_CONTENT_SIGNAL` | ≥ 3 years | Finding catalogue | None | Pilot |
| P-07 | `SITE_DOWN` confirmation | 3 attempts over ≥ 24 h | Finding catalogue | None | Pilot |
| P-08 | `NO_SITE` confirmation | 2 independent sources for `KNOWN` | Finding catalogue | None | Pilot |
| P-09 | Mobile contact path window | first 2 screens at 360×800 | Finding catalogue | None | Pilot |
| P-10 | Pages per site | ≤ 20 | Fetcher | None | M2b approval |
| P-11 | Request rate per domain | ≤ 1 request / 2 s | Fetcher | None | M2b approval |
| P-12 | Activity window for `G_ACTIVE` | 12 months | Scoring gates | None | User / pilot |
| P-13 | Bucket thresholds | see [data-contracts § 6.4](data-contracts.md#64-buckets-hypothesis) | Scoring | None | Calibration with human labels |
| P-14 | Category value bands | **none set** | Scoring (BV component) | — | **User decision** (PD-17); until then BV is `UNKNOWN` for real data, synthetic in fixtures |
| P-15 | Detector precision / recall on fixture corpus | ≥ 0.95 / ≥ 0.90 | M2a acceptance | None | User approval of M2a criteria |
| P-16 | Human agreement with pilot findings | ≥ 90 % | M2b acceptance | None | User |
| P-17 | Reviewer agreement for scoring calibration | ≥ 70 % | M4 acceptance | None | User |
| P-18 | Retries | 3 attempts, base 2 s ×2; 2 regenerations; dead-letter after 3 | Failure strategy | Common practice | Later phases |
| P-19 | Circuit breaker | open after 5 failures; half-open after 5 min | Failure strategy | None | Later phases |
| P-20 | Budget reserve and alerts | reserve 10 %; alerts at 50/80/100 % | Budget | None | User |
| P-21 | Approval expiry | 7 days (most), 48 h (budget), 24 h (other external writes) | Approvals | None | User |
| P-22 | Retention periods | non-qualified leads 6 months; contacted 12 months; raw captures 90 days; suppression hashes indefinite | Data protection | None — **requires legal review** | Counsel (PD-13, PD-24) |
| P-23 | Preview expiry / takedown | ≤ 30 days / 1 business day | Previews | None | Preview phase |
| P-24 | T2 quota | **none set** | Tiers | — | User |
| P-25 | Agent token envelopes | see agent-design § 3 | Agents | Rough guess | Measured when agents are approved |
| P-26 | Factory quality targets (Lighthouse, LCP, CLS, TBT, JS, transfer, fonts) | see [quality-gates § 2](quality-gates.md#2-quality-profiles) | Factory QA | Targets we choose; achievability not demonstrated | Reference site (M6a) |
| P-27 | Design rubric thresholds | ≥ 3.5/5 preview; ≥ 4/5 production, no criterion < 3 | Factory QA | None | Rubric definition (PD-25) |
| P-28 | Dependency policy | release in last 12 months; minimum release age 14 days | Admission policy | Common practice | User |
| P-29 | Agent eval thresholds | see agent-design § 6 | Agents | None | When agents are approved |
| P-30 | Dashboard lag | ≤ 2 s at 50 events/s | Dashboard | None | Dashboard phase |
| P-31 | Lighthouse re-measure margin | 3 points | QA | None | M2a measurements |
| P-32 | Confidence band definition | see [data-contracts § 6.5](data-contracts.md#65-confidence-band-hypothesis) | Scoring | None | Calibration |
| P-33 | Funnel volumes and conversion rates | **none set** (symbolic) | Cost model | — | Measured |
| P-34 | Kill-switch polling interval | **none set** | Later phases | — | Later phases |

## Hypotheses

| ID | Hypothesis | How it would be tested |
|---|---|---|
| H-1 | Small local service businesses in the target area often have websites with measurable mobile, performance or contact-path gaps | M2b pilot, base rates per finding |
| H-2 | Findings with high acquisition impact, in an active business of a valuable category, indicate an opportunity worth a sales conversation | Pilot P1: second human label + outcomes |
| H-3 | A free diagnosis offered through a lawful first-contact channel generates requests for the report | Pilot P1, after legal review |
| H-4 | The acquisition-impact table (`impact_rules.v1`) reflects how problems affect customer acquisition | Pilot P1 |
| H-5 | A static Astro site built from a component library can meet the provisional quality targets (P-26) | Reference site M6a |
| H-6 | "Southeast Madrid" ≈ Puente de Vallecas, Villa de Vallecas, Moratalaz, Vicálvaro, Rivas-Vaciamadrid, Arganda del Rey | User confirmation (PD-12) |
| H-7 | Many sites in the target segment score poorly on lab performance, so `SLOW_MOBILE` may discriminate weakly | Pilot base rates |
| H-8 | Relative costs T1 < T2 < T3 | Measured once generation exists |

## Unknowns

| ID | Unknown | Blocks |
|---|---|---|
| U-1 | LLM provider, model mapping, prices | Any agent phase |
| U-2 | Discovery sources that pass a terms/licence review | M4 |
| U-3 | Preview delivery (private hosting vs local screenshots/PDF) | Preview phase |
| U-4 | Agency legal identity, website and opt-out contact | M2b, any contact |
| U-5 | Answers to the legal questions in [security-and-compliance § 12](security-and-compliance.md#12-questions-for-counsel) | M2b, P1, M4, M8 |
| U-6 | Price ranges per tier | Sales phase |
| U-7 | Content of OI's private copy | Only if detailed pilot learnings are needed |
| U-8 | Whether OI will converge its two `source_class` vocabularies | OI bridge (deferred) |

## Pending decisions

### Blocking M1 implementation

| ID | Decision | Options / notes |
|---|---|---|
| PD-01 | Authorize M1 implementation | **Not given.** Only the documentation correction is authorized. |
| PD-02 | Test and schema-validation dependencies | (a) standard library only: `unittest` + an in-house subset validator, as OI does; (b) `pytest` + `jsonschema` after an admission review. |
| PD-03 | Repository visibility (public or private) | Determines what documentation and fixtures may contain. |
| PD-04 | M1 execution environment and Python version | This cloud container or a local machine. SQLite features (STRICT tables, JSON functions) must be checked there at implementation start. |
| PD-05 | Hash chain in the event log | Recommended (tamper evidence, not tamper proof); optional for M1. |
| PD-06 | Documentation language | The design documents are in English, the review is in Spanish. |
| PD-07 | Operator identity for CLI approvals | Self-declared OS user name or a configured operator list. Neither is authentication (see architecture § 6.3). |

### Required before M2a (diagnosis engine on local fixture sites only)

| ID | Decision |
|---|---|
| PD-08 | Sandboxed execution environment for Chromium and the admission review of Playwright, Lighthouse and axe-core (and the Node.js version). |
| PD-09 | Approval of the finding catalogue v1 and of the acquisition-impact hypothesis table. |
| PD-10 | Who builds and labels the fixture corpus. |

### Required before M2b (real-site diagnosis pilot) and pilot P1

| ID | Decision |
|---|---|
| PD-11 | Agency legal identity, website and opt-out contact (needed for the crawler's User-Agent and for any notice). |
| PD-12 | Target area definition and one initial category. |
| PD-13 | Legal basis for analysing real business websites, including sole traders' (counsel; legitimate-interest assessment). |
| PD-14 | Capture retention policy (what is kept after raw captures are deleted; legal periods). |
| PD-15 | Source of the pilot site list. |
| PD-16 | Success criteria for pilot P1 (set by the user before it starts). |

### Deferrable

| ID | Decision | Needed before |
|---|---|---|
| PD-17 | Category value bands (P-14) | Real scoring (M4) |
| PD-18 | LLM provider and monthly cap | First agent phase |
| PD-19 | Preview delivery and hosting | Preview phase |
| PD-20 | Price ranges per tier | Sales phase |
| PD-21 | Whether T2 requires the prospect's prior request | Preview phase |
| PD-22 | Lawful outreach channels and mandatory notices | Any contact (P1, M8) |
| PD-23 | Analytics approach for production sites (cookieless or consent-based) | Factory/production |
| PD-24 | DPIA requirement and retention periods | Before real personal data at scale (M4) |
| PD-25 | Who reviews design, and the rubric criteria | M6a |
| PD-26 | AgentScope evaluation, OI bridge, PostgreSQL, dashboard technology, Google Sheets, CRM | Their respective phases |

## Correction log (E1–E10)

| ID | Contradiction found in the review | Correction | Where |
|---|---|---|---|
| E1 | Diagram listed Lighthouse CI despite D-012 | Diagram now lists Lighthouse (Node API) | architecture § 4.2 |
| E2 | Scoring gates needed evidence produced only later by the LLM research agent | Deterministic extraction of basic site facts in the diagnosis stage; human-review evidence allowed for gates; gates may stay `UNKNOWN` (lead stays `PENDING`) | architecture § 5, data-contracts § 6.3, roadmap M2a |
| E3 | Opportunity bucket required contact eligibility, which depends on legal review scheduled later | Contactability removed from the score (D-023) | data-contracts § 6, architecture § 5.2 |
| E4 | Real-site pilot processed sole traders' data before the legal basis was documented | Legal basis (PD-13) is an entry requirement of M2b | roadmap § 2, security § 4 |
| E5 | Crawler User-Agent needed an agency identity that was unknown until much later | Agency identity (PD-11) is an entry requirement of M2b | roadmap § 2, security § 5.2 |
| E6 | Raw captures deleted after 90 days while `KNOWN` evidence required a capture for re-verification | Evidence keeps snippet + capture hash; a `capture_available` flag records whether re-verification is still possible; retention periods are PENDING (P-22) | data-contracts § 3, security § 4 |
| E7 | Approvals needed before the dashboard existed | CLI approvals are part of M1 | roadmap M1 |
| E8 | Relative tier costs and token envelopes presented without basis | Marked HYPOTHESIS (H-8, P-25) | architecture § 5.3, agent-design § 3 |
| E9 | "Replay rebuilds identical read model" implied full event sourcing | Removed; D-022 | roadmap M1 |
| E10 | Retention periods and thresholds without basis | Moved to the provisional parameters register | this document |
