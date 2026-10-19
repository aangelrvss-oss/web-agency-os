# Web Agency OS

A planned operating system for a premium web agency that sells websites to small local businesses. It would find
businesses whose websites have **objectively verifiable** problems, keep technical evidence separate from commercial
judgement, prioritize leads for human review, and — only in later, separately approved phases — generate previews,
prepare sales material and track a pipeline.

## Status

Phase 0 documentation has been reviewed and corrected ([docs/phase0-review.md](docs/phase0-review.md), in
Spanish). **M1 (minimal deterministic core) is implemented** — see [M1 core](#m1-core-implemented). Nothing beyond M1
is implemented.

Decided for M1 (D-018, D-019): a local Python + SQLite program with no AI, no paid APIs, no network connections and
synthetic data only, covering JSON contracts, evidence, deterministic three-layer scoring, a state machine, an
append-only event log, CLI approvals bound to the exact action hash, spend control and safe CSV export. Excluded in this
phase: OI code integration, PostgreSQL, dashboard, AgentScope, Google Sheets.

Out of scope until their phase requirements are approved (D-020): crawling real websites, commercial contact, public
deployment, automatic preview generation.

| Document | Contents |
|---|---|
| [docs/decisions.md](docs/decisions.md) | Status labels, decisions, verification status, provisional parameters, hypotheses, pending decisions, correction log |
| [docs/roadmap.md](docs/roadmap.md) | Phases, gated activities and entry requirements, full M1 specification with 12 acceptance tests, costs and spend control |
| [docs/architecture.md](docs/architecture.md) | OI audit, principles, target architecture, three-layer workflow, state machine, SQLite/event-log design and limitations |
| [docs/data-contracts.md](docs/data-contracts.md) | M1 core contracts, three-layer assessment, events, approvals, ledger, suppression, CSV format |
| [docs/security-and-compliance.md](docs/security-and-compliance.md) | Legal claims and their status, threat model, data protection, dependency admission, tests before running third-party tools |
| [docs/quality-gates.md](docs/quality-gates.md) | Website factory, conversion components, scroll-animation rules, design rubric, quality profiles |
| [docs/agent-design.md](docs/agent-design.md) | Agents for later phases, permissions, how their actions are recorded |
| [docs/phase0-review.md](docs/phase0-review.md) | Critical review of Phase 0 (Spanish) and how each finding was incorporated |

## M1 core (implemented)

A local command-line program: Python 3 standard library + SQLite. No AI, no paid APIs, no network code, synthetic
data only. Tested with Python 3.13.16 and SQLite 3.45.1 (STRICT tables and JSON functions available).

```bash
python3 -m unittest discover -s tests -t .            # acceptance tests AT1.1–AT1.12 (network blocked)

python3 -m waos --db demo.sqlite3 import fixtures/synthetic_demo.json
python3 -m waos --db demo.sqlite3 transition lead_demo_01 IDENTITY_RESOLVED
python3 -m waos --db demo.sqlite3 transition lead_demo_01 DIAGNOSED
python3 -m waos --db demo.sqlite3 score lead_demo_01
python3 -m waos --db demo.sqlite3 transition lead_demo_01 SCORED
python3 -m waos --db demo.sqlite3 approve request --type SHORTLIST --lead lead_demo_01
python3 -m waos --db demo.sqlite3 --operator ana approve decide <approval_id> APPROVED
python3 -m waos --db demo.sqlite3 --operator ana transition lead_demo_01 SHORTLISTED --approval <approval_id>
python3 -m waos --db demo.sqlite3 export csv --out exports/leads_SYNTHETIC.csv
python3 -m waos --db demo.sqlite3 trace lead_demo_01
```

Other commands: `leads`, `evidence add`, `budget show|apply`, `tool call` (fake tools only), `suppress`, `erase`,
`retention run`, `verify`. Layout: `waos/` (code), `contracts/` (8 JSON Schemas), `rules/` and `config/` (versioned
rules and provisional parameters), `fixtures/` (synthetic demo), `tests/`.

Implementation choices taken for M1 (pending decisions in [docs/decisions.md](docs/decisions.md)): PD-02 → standard
library only (`unittest` + an in-house JSON Schema subset validator; unsupported keywords raise); PD-05 → no hash chain;
PD-07 → `--operator NAME` is self-declared, not authenticated.

Known limitations:

- SQLite allows one writer at a time; fine for a local single-operator CLI only.
- The append-only triggers on `events` protect against program bugs, not against someone with access to the file;
  without a hash chain there is no tamper evidence. An existing database with a missing trigger is refused, not repaired.
- The database is not encrypted; only synthetic data is accepted (`REAL` is rejected on import, by CHECK constraints
  and on export).
- Erasing personal data also removes the raw capture text it came from, so other evidence from that capture can no
  longer be re-verified (`capture_available = false`).
- All thresholds, value bands, expiry and retention durations are provisional hypotheses (`P-xx`); the fixture's
  value bands are synthetic.
- No global kill switch command (per-lead `ON_HOLD` only); `score all` scores every lead regardless of state.
- IDs are time-ordered hex strings, not ULIDs. A denied metered call without a budget is recorded as `NO_BUDGET`
  (the roadmap's `BUDGET_REQUIRED`).
- Values starting with `+`, `-`, `=` or `@` (including phone numbers such as `+34 …`) are exported with a leading `'`.

## M2a static diagnosis (first demo)

```bash
python3 -m waos demo-m2a          # fresh DB in demo_out/m2a, diagnoses corpus/m2a, prints labels vs results
```

`corpus/m2a/` holds 17 synthetic local sites; each `site.json` states its test purpose and expected results (labels
written by Claude, PD-10, provisional). Only local files are read (no network, no browser). Checks decidable from HTML
(`SEO_BASICS_MISSING`, `NO_LOCAL_SIGNALS`, `BROKEN_INTERNAL_LINKS`) can return NOT_DETECTED; `MIXED_CONTENT`,
`NOT_MOBILE_READY` and `NO_MOBILE_CONTACT_PATH` can only be DETECTED or UNKNOWN; `NO_HTTPS`, `TLS_INVALID`, `SITE_DOWN`,
`SLOW_MOBILE`, `LAYOUT_SHIFT` and `A11Y_SERIOUS` are always UNKNOWN until a browser/network phase (PD-08) is approved.
UNKNOWN findings only raise score ceilings. Captures are stored as raw HTML (no sanitizer yet).

### M2a.1 diagnosis audit

The same command now diagnoses 17 sites (edge cases: valid variations, several defects, malformed HTML, encoded and
relative links, ambiguous place names, contradictory evidence, no home page, crawl limit, WhatsApp/form-only contact
and no usable contact channel) and writes, with a fixed clock (`as_of` in `corpus.json`) so every run is byte-identical:

- `demo_out/m2a/audit_report.md` — readable audit in Spanish: executive summary, evaluation status and review
  priority, confirmed problems with their evidence, unverified checks and why, commercial impact as a separate
  hypothesis, recommendations for human review. No contact values, page HTML, evidence ids or invented figures.
- `demo_out/m2a/report.json` — expected vs actual per site (`deviations`, known or unexpected), detector tally and
  evaluation matrix.
- `demo_out/m2a/leads_SYNTHETIC_m2a.csv` — M1 columns plus `evaluation_status`, `evaluation_procedure`,
  `checks_unverified` (appended).

Evaluation status (D-026) is separate from the review bucket: `PROBLEMS_FOUND` (a problem confirmed by valid evidence),
`NO_PROBLEMS_FOUND` (the three statically decidable checks completed without a problem — the other nine stay listed as
unverified, so it is not a guarantee), `INSUFFICIENT_EVIDENCE` (one of those checks is still UNKNOWN). See
[corpus/m2a/README.md](corpus/m2a/README.md) for the cases, their expectations and the first-run log.

## Non-negotiable rules

- Deterministic code decides state transitions, budgets, authorization, scoring and QA; agents (later) only propose.
- A technical score is never interpreted as purchase intent; `purchase_intent` stays `UNKNOWN` unless a human records an
  interaction with the prospect.
- No shell, filesystem or raw network access for agents; one gateway for all tools.
- External content is untrusted data, never instructions.
- Human approval before any commercial communication, publication, budget change or external write. No automatic
  sending exists.
- No paid API calls, external accounts, deployments or real customer data without an explicit decision.
- Legal statements, dependency advisories and OI test results are labelled REPORTED or not verified; nothing is
  presented as independently verified when it is not. Numeric thresholds are provisional hypotheses.

## Relationship with Opportunity Intelligence (OI)

[aangelrvss-oss/OI](https://github.com/aangelrvss-oss/OI): `main` contains only a README; the implementation is on branch
`claude/zealous-archimedes-qb70kr` (commit `19aeeb8`). WAOS reuses OI's evidence vocabulary and rule designs by
re-implementing them; no OI code is integrated in this phase. OI was read, not executed, and not modified.
