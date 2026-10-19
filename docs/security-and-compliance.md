# Web Agency OS — Security and Compliance Model

Revision: Phase 0, corrected after the Phase 0 review ([phase0-review.md](phase0-review.md)). Date: 2026-10-19.
Status: **design only.** Labels (VERIFIED, REPORTED, HYPOTHESIS, PENDING): [decisions.md](decisions.md#status-labels).

> **Not legal advice.** Nothing here is a legal conclusion. Legal statements are at most **REPORTED** — read by the
> Phase 0 research subagent in the cited sources — and none was independently verified. They must be confirmed by a
> qualified Spanish lawyer before any activity that depends on them. Where a statement is a preliminary engineering
> reading, it is labelled as such. Conservative defaults are used until counsel answers.

## 1. Legal position (status: REPORTED, not legal advice)

### 1.1 Legal claims and their verification status

| # | Statement used in the design | Source cited in Phase 0 | Status | Needed before |
|---|---|---|---|---|
| L1 | LSSI (Ley 34/2002) Art. 21 prohibits unsolicited commercial communications by email or equivalent electronic means without prior request or express authorization; the annex defines the recipient as a natural **or legal** person; Art. 21.2 has an exception for a prior contractual relationship | BOE-A-2002-13758 (read by the research subagent) | REPORTED — read the text directly and confirm with counsel | Any contact |
| L2 | Web contact forms, WhatsApp, SMS and social-network messages count as "equivalent electronic means" | None (conservative reading) | PENDING | Any contact |
| L3 | Ley 11/2022 (LGTel) Art. 66.1.b: right not to receive unsolicited commercial calls without consent or another legal basis, applicable since 29 June 2023; AEPD Circular 1/2023 interprets it | AEPD press note; BOE text not quoted | REPORTED — verify in BOE and the Circular | Phone contact |
| L4 | Differences between calling companies and calling sole traders | — | PENDING | Phone contact |
| L5 | LOPDGDD Art. 19: presumption of legitimate interest for contact data of sole traders and professionals in that capacity | BOE (subagent) | REPORTED | Any real personal data |
| L6 | LOPDGDD Art. 23.4: prior consultation of advertising exclusion systems (e.g. Lista Robinson); which channels and how often | BOE (subagent) for the article; scope not established | REPORTED / scope PENDING | Any contact |
| L7 | GDPR Art. 14: information duties when data is not collected from the person, including timing at first contact | Recalled, not re-checked | PENDING | Any contact; any real personal data |
| L8 | Whether a DPIA is required | — | PENDING | M4 |
| L9 | Passive analysis of identifiable sole traders' websites needs a documented legal basis even without contact | Preliminary engineering reading | PENDING | M2b (fixes E4) |
| L10 | Using a prospect's name or logo in a private preview (IP, trademarks) | — | PENDING | M7 |
| L11 | Retention periods for leads, captures and suppression entries | None (P-22 values are HYPOTHESIS) | PENDING | Any real personal data |
| L12 | EU AI Act Art. 50 transparency duties apply from 2 August 2026, with a reported grace period for machine-readable marking to 2 December 2026 | Secondary sources, medium confidence | REPORTED — verify on EUR-Lex | AI-generated content on client sites |
| L13 | European Accessibility Act: microenterprise exemption for services; Spanish transposition | Recalled, not re-checked | PENDING | Client sites with e-commerce |
| L14 | Text-and-data-mining reservations (DSM Directive Art. 4) and their Spanish transposition | Recalled, not re-checked | PENDING | M2b |
| L15 | Google Maps Platform / Places terms: only `place_id` storable indefinitely; lat/lng ≤ 30 days; no other caching; no display on non-Google maps | Google terms pages (subagent) | REPORTED — re-check current terms | Any Google API use |
| L16 | Reuse conditions of BORME and municipal open data | — | PENDING | M4 |
| L17 | Rules on misleading claims in B2B sales material | — | PENDING | M8 |
| L18 | LSSI Art. 10 legal-notice and cookie-consent duties for client sites | Recalled | PENDING | Production sites |
| L19 | Validity and proof of verbal consent obtained by phone for later email | — | PENDING | Any email follow-up |

### 1.2 Consequences for the design (conservative defaults until counsel answers)

- No contact of any kind is in scope (D-020). When contact is approved, email and other electronic messages are treated
  as not allowed without recorded consent or a prior contract (L1, L2); phone and postal contact are treated as
  conditional on checks (L3–L7).
- The business model idea "first contact by phone, post or in person offering a free diagnosis; email only after the
  prospect asks" is a **hypothesis** (H-3) that depends on L1–L7 and L19.
- No real personal data is processed in M1 (synthetic only). Real-site analysis (M2b) requires PD-13.

## 2. Threat model

| # | Threat | Phase | Controls |
|---|---|---|---|
| T1 | Real personal data enters a synthetic-only phase | M1 | `data_mode = REAL` rejected on import and export; fixtures use `.example` domains and reserved test numbers |
| T2 | Personal data becomes impossible to erase | M1+ | Events carry ids and hashes only (D-024); erasure in state tables; test AT1.8 |
| T3 | Bypass of the spend switch or approvals | M1+ | Single gateway; double switch; approvals bound to `action_sha256`; tests AT1.4, AT1.7, AT1.11 |
| T4 | Tampering with the event log | M1+ | Triggers (protect against bugs only); optional hash chain (tamper evidence); limitations in [architecture § 6.3](architecture.md#63-limitations-to-be-stated-in-the-m1-readme-when-implemented) |
| T5 | Spreadsheet formula injection | M1+ | Escaping and quoting rules; test AT1.9 |
| T6 | Malicious website content attacking the headless browser | M2a+ | Sandboxed container; non-root; read-only FS; no credentials; downloads disabled; resource limits; browser kept current. **Chromium's own sandbox is often disabled inside containers (`--no-sandbox`), which weakens isolation — status in the chosen environment is PENDING (PD-08).** |
| T7 | SSRF through the fetcher | M2a+ | Block private, loopback (except the M2a test server), link-local, CGNAT, multicast and metadata ranges (IPv4/IPv6); pin resolved IP per connection; re-check redirects; ports 80/443 |
| T8 | Supply-chain compromise (npm/PyPI) | M2a+ | Admission policy (§6) |
| T9 | Prompt injection via websites | M5+ | Untrusted content as data; agents with untrusted input have no external-write tools, no secrets, no cross-lead access; injection eval suite |
| T10 | Secret leakage and cost exhaustion | M5+ | No credentials until a paid phase; secrets only in the gateway; provider-side caps |
| T11 | Dashboard XSS/CSRF | M3+ | Captures rendered as text; previews on a separate origin; CSP; CSRF tokens; authentication |
| T12 | Misleading sales claims | M8 | Measurement date and tool on every claim; `sales_safe`; claim detector; no generated testimonials |
| T13 | Allegation of unauthorized security testing | M2b+ | Passive-only rules (§5.2); no security findings |

## 3. Runtime controls

**M1:** no network code paths; socket and DNS lock during tests; no credentials present; no agents; synthetic data only;
no external writes; the paid-call switch is off in two places; kill switch command; startup integrity check of the
database (triggers, foreign keys).

**Later phases:** workers in containers (non-root, read-only root FS, `no-new-privileges`, capabilities dropped, seccomp,
CPU/memory/pids/time limits); egress per worker (fetcher: public web through the SSRF guard; builder: none; QA:
loopback); agents without shell, filesystem, code execution or raw network (these tools do not exist in the registry).

## 4. Personal data protection

| Topic | Rule |
|---|---|
| M1 | Synthetic data only. Synthetic personal values exist only to test the privacy rules. |
| Before real data | Legal basis documented and reviewed by counsel (L5, L9; PD-13); retention periods decided (L11, P-22); storage protection decided (SQLite is not encrypted at rest); DPIA decision (L8). These are entry requirements of M2b/M4 (fixes E4). |
| Scope (later) | Business-level data first; personal data limited to business contact details published by the business itself; no private profiles, no special categories, no inferred traits about individuals. |
| Event log | Never contains personal-data values (D-024). |
| Captures and evidence | Evidence keeps the snippet and the capture's SHA-256; when the raw capture is deleted, `capture_available = false` and the evidence can no longer be re-verified (fixes E6). What is kept and for how long is PENDING (PD-14). |
| Suppression | Salted hashes of identifiers; pseudonymous data may still be personal data; treatment PENDING (L11). |
| Rights | Objection → suppression across all channels; erasure → values removed from state tables, ids and hashes kept. |
| Processors | Any LLM, hosting or email provider requires a data-processing agreement before use (later). |
| Breach | Incident runbook (§13); notification duties to be confirmed by counsel. |

## 5. Public data collection (later phases; gated)

### 5.1 Sources

| Source type | Status |
|---|---|
| Business's own website | Candidate for M2b, under §5.2 and PD-13 |
| Official registries and open data | Candidate after a per-source reuse-terms review (L16) |
| Operator-prepared CSV | Candidate; the operator documents the source of each list |
| Business directories | Blocked until a terms and database-right review per directory |
| Google Maps / Places | Not for scraping; API use only if current terms allow the use case (L15; D-015) |
| Social networks, paid data brokers | Blocked by default |
| OI import | Deferred (D-001) |

### 5.2 Passive-diagnosis rules (no security testing)

- Only GET/HEAD of URLs linked from the site or listed in its sitemap; page limit P-10; rate limit P-11; back off on 429/503.
- An identifying User-Agent with a URL describing the crawler and an opt-out contact. **This requires the agency's
  identity and website (PD-11), an entry requirement of M2b (fixes E5).**
- robots.txt and text-and-data-mining reservations honoured (L14).
- No form submission, logins, search-box fuzzing, directory guessing, port scanning, version or vulnerability probing,
  CAPTCHA solving, or circumvention of any access control.
- No security findings recorded or reported.

## 6. Supply chain and dependency admission

### 6.1 Verification status

All dependency facts in [decisions.md § Dependency assessment](decisions.md#dependency-assessment) are **REPORTED**. Not
done for any package: transitive tree audit, install-script review, sandboxed first execution, licence check of
transitive dependencies. Not assessed at all: `pytest`, `jsonschema`, HTML validator, JSON-LD checker, dashboard
framework, PostgreSQL driver. OI was read but never executed; its tests were not reproduced.

### 6.2 Admission policy

A dependency is admitted only when all apply:

1. Licence in the allowlist (MIT, Apache-2.0, BSD-2/3-Clause, ISC, MPL-2.0 used unmodified, OFL-1.1 for fonts); LGPL
   needs a recorded decision; GPL/AGPL/SSPL/proprietary denied by default.
2. Maintained (P-28) or a written justification.
3. No unpatched high/critical advisory at the pinned version (checked at admission and continuously).
4. Transitive tree reviewed: size, install scripts, native binaries, network activity.
5. Exact versions pinned in a lockfile with integrity hashes; minimum release age for non-security upgrades (P-28).
6. SBOM generated and kept with each build.

### 6.3 Tests required before executing any third-party tool

1. Install from a lockfile with integrity hashes and install scripts disabled; review any script that is required.
2. Generate the SBOM and scan the complete tree against an advisory database.
3. First execution inside a container with no network, no credentials, non-root, resource limits, logging every network
   attempt and every file write outside scratch space.
4. Execute against local fixtures only.
5. Record the status of the Chromium sandbox in that environment and decide whether it is acceptable (PD-08).
6. Pass the SSRF suite.
7. Only then, a limited and approved real run (M2b).

## 7. Asset provenance and intellectual property (later phases)

Every asset has an `AssetRecord`. Prospect photos and logos: private previews only (`PREVIEW_ONLY`), and only if counsel
allows it (L10); written client permission before production. Text from prospect sites is not copied into production
copy. Stock assets only under licences allowing commercial web use. Fonts self-hosted under OFL or commercial licences.
AI-generated images only for abstract imagery, never realistic depictions of real people, the client's team, premises or
work (L12). Testimonials, reviews, ratings, awards, certifications, client logos, project counts and years in business
are never generated.

## 8. External APIs and accounts (later phases)

Onboarding checklist per provider: terms allow the use case; data-processing terms; data location and retention;
prices recorded in `pricing.v1.json`; rate limits; provider-side cap; least-privilege key; separate keys per environment;
rotation; usage endpoint for reconciliation. No accounts were created and no keys used in Phase 0.

## 9. Contactability and outbound communications (later; gated)

Contactability is separate from opportunity scoring (D-023) and computed by deterministic policy once counsel has
answered L1–L7 and L19. Conservative defaults for that future policy:

| Channel | Default | Becomes usable only with |
|---|---|---|
| Email, SMS, WhatsApp, social DM, web form | `NOT_ELIGIBLE` | Recorded consent or prior contract, per counsel (L1, L2, L19) |
| Phone | `UNKNOWN` until counsel answers | Conditions defined by counsel (L3, L4, L6, L7) |
| Postal | `UNKNOWN` until counsel answers | Conditions defined by counsel (L5–L7) |
| In person | `UNKNOWN` until counsel answers | Conditions defined by counsel (L7) |

The system has no sending capability; a human contacts the prospect after an approval for the exact text and channel.
Every communication would need: sender identity (PD-11), data source, purpose, how to object, privacy-notice link,
claims stated as lab tests with date and tool, no pressure tactics, no impersonation.

## 10. Human approvals

| Type | Phase | Purpose |
|---|---|---|
| `SHORTLIST` | M1 | Move a `REVIEW_PRIORITY` lead to `SHORTLISTED` |
| `BUDGET_CHANGE` | M1 | Change any cap (explicit new number) |
| `CAMPAIGN_PLAN` | M2b+ | Approve a real-site list, sources, quotas |
| `PREVIEW_T2`, `OUTREACH`, `PUBLISH`, `EXTERNAL_WRITE`, `DATA_SOURCE_ENABLE`, `EXTERNAL_DESTINATION` | later | Defined; no executor in this phase |

Every approval is bound to the SHA-256 of the exact action, expires (P-21), is decided by a human and executes at most
once ([data-contracts § 8](data-contracts.md#8-approvalrequest)). In M1 the operator identity is self-declared.

## 11. Previews and publication (later; gated)

Private access or signed expiring URLs (P-23); `noindex`; no analytics, forms or third-party requests; a visible banner
"Propuesta conceptual preparada por <agencia>. No es la web oficial de <negocio>."; never hosted on a domain resembling
the business's name; takedown on request. Publication requires client sign-off, the production quality profile, legal
pages (L18), verified licences and a `PUBLISH` approval.

## 12. Questions for counsel

1. L1, L2: scope of LSSI Art. 21 for B2B and for forms, WhatsApp, SMS and social messages.
2. L3, L4, L6: conditions for commercial calls to companies and to sole traders; exclusion-list checks per channel.
3. L5, L9: legal basis for passively analysing business websites, including sole traders', before any contact.
4. L7: wording and timing of the information to give at first contact by each channel.
5. L8: is a DPIA required?
6. L10: may a private preview use the prospect's name or logo, and under what conditions?
7. L11: retention periods for leads, captures and suppression entries.
8. L12–L14: AI Act transparency, accessibility obligations and text-and-data-mining reservations relevant to us.
9. L16: reuse conditions for BORME and municipal open data.
10. L17, L18: rules for claims in sales material; legal pages and cookies on client sites.
11. L19: validity and proof of consent given by phone.

## 13. Logging, audit and incidents

All approvals, transitions, tool calls, costs and policy decisions are events (no personal values). Incident runbook:
kill switch → revoke keys (when any exist) → preserve the database file with SQLite's backup API → assess personal-data
impact → notify where required (to be confirmed by counsel) → post-mortem recorded as a decision.
