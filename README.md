# Web Agency OS

A planned operating system for a premium web agency that sells websites to small local businesses. It would find
businesses whose websites have **objectively verifiable** problems, keep technical evidence separate from commercial
judgement, prioritize leads for human review, and — only in later, separately approved phases — generate previews,
prepare sales material and track a pipeline.

## Status

**Design only. Nothing is implemented.** Phase 0 documentation has been reviewed and corrected
([docs/phase0-review.md](docs/phase0-review.md), in Spanish). **M1 implementation is not yet authorized.**

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
