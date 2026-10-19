# Web Agency OS

An operating system for a premium web agency that sells websites to small local businesses. It finds businesses with
**objectively verifiable** website problems, ranks the opportunity, researches the best candidates, chooses the right
website scope, generates tailored Astro previews only for high-confidence leads, runs quality gates, prepares sales
material and keeps a traceable pipeline. A dashboard shows real agent events, tasks, sources, costs, errors and approvals.

## Status: Phase 0 (architecture only)

There is **no implementation yet**. This repository contains the Phase 0 design:

| Document | Contents |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Workspace/Git audit, OI audit and reuse map, architecture diagram, workflow and state machines, data flow, failure/retry strategy, budget rules, dashboard specification |
| [docs/agent-design.md](docs/agent-design.md) | Agents vs deterministic services, responsibility and tool-permission matrix, runner contract, prompt-injection controls, evals |
| [docs/data-contracts.md](docs/data-contracts.md) | Evidence, findings, leads, scoring rules, contact/consent, manifests, assets, approvals, ledgers, spreadsheet fields |
| [docs/security-and-compliance.md](docs/security-and-compliance.md) | Threat model, supply-chain policy, GDPR/LOPDGDD, LSSI, data collection, asset provenance, contact eligibility, approvals |
| [docs/quality-gates.md](docs/quality-gates.md) | Astro website factory and measurable gates (performance, accessibility, SEO, content, design review) |
| [docs/roadmap.md](docs/roadmap.md) | Milestones with acceptance tests, stop conditions, cost model template, Phase 0 recommendation |
| [docs/decisions.md](docs/decisions.md) | ADRs, dependency assessment, assumptions, unknowns, decisions needed |

## Non-negotiable rules

- Agents propose; deterministic code decides state transitions, budgets, authorization, eligibility and QA.
- Agents have no shell, no filesystem and no raw network; all tools go through one gateway.
- Website content and other external text are untrusted data, never instructions.
- Human approval is required before commercial communications, publishing anything, raising a budget or any external
  write. The system has no automatic sending capability.
- No paid API calls, external accounts, deployments or real customer data without an explicit decision.
- Expensive generation is reserved for high-confidence, high-priority opportunities (tiers T0–T3).
- Assumptions and unknowns are recorded; nothing is invented.

## Relationship with Opportunity Intelligence (OI)

[aangelrvss-oss/OI](https://github.com/aangelrvss-oss/OI): `main` contains only a README; the implementation lives on
branch `claude/zealous-archimedes-qb70kr` (public edition, commit `19aeeb8`). Web Agency OS stays independent and
integrates through versioned JSON contracts (`evidence_input.v1`, `opportunity_record.v1`), reusing OI's evidence
vocabulary and rule designs, not its code. Phase 0 did not modify OI.

## Key Phase 0 findings

1. Spanish law (LSSI Art. 21) prohibits unsolicited commercial email even to companies; first contact must be phone,
   post or in person, with email only after consent. Legal review is a precondition for outreach.
2. Build first, without LLMs or paid APIs: contracts and control plane (M1), the website-diagnosis engine (M2), and
   the dashboard (M3).
3. AgentScope 2.0 is evaluated only in a sandboxed spike; its standalone Studio is archived. Lighthouse CI is stale, so
   Lighthouse 13 is used directly. Astro must be ≥ 7.2.8 (critical image-pipeline advisory).
