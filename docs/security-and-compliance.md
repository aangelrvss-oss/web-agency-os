# Web Agency OS — Security and Compliance Model (Phase 0)

Status: **proposal, not implemented**. Date: 2026-10-19.

> **Not legal advice.** This document records an engineering reading of the rules that appear relevant, with sources
> where they were checked. Before the system collects real personal data at scale (milestone M4) and before any outreach
> (milestone M8), a Spanish data-protection / commercial-law professional must review it. Items marked **VERIFY** were
> not confirmed against a primary source in Phase 0.

## 1. Key findings that change the business design

1. **Cold commercial email is not a viable first-contact channel in Spain, even business-to-business.** LSSI-CE
   (Ley 34/2002) Art. 21.1 prohibits commercial communications by email or equivalent electronic means that were not
   previously requested or expressly authorised by the recipient, and the Act's annex defines the recipient
   (*destinatario*) as a natural **or legal** person. The only exception (Art. 21.2) is a prior contractual relationship
   with similar products. GDPR legitimate interest does not override this. Source: BOE-A-2002-13758 (checked 2026-10-19).
   Consequence: the system never sends email (or WhatsApp/SMS/social DMs/web-form messages, treated as equivalent
   electronic means until counsel says otherwise) to a prospect without a recorded consent or a prior contract.
2. **Phone and postal first contact are possible only with checks.** Since 29 June 2023, Ley 11/2022 (General de
   Telecomunicaciones) Art. 66.1.b gives users the right not to receive unsolicited commercial calls unless there is
   consent or another legal basis such as legitimate interest; AEPD Circular 1/2023 interprets it (source: AEPD press
   note; BOE text not quoted — **VERIFY**). LOPDGDD (Ley Orgánica 3/2018) Art. 23.4 requires checking advertising
   exclusion systems (e.g. Lista Robinson) before direct marketing to people who have not consented.
3. **Sole traders' business data is personal data.** LOPDGDD Art. 19.2 presumes legitimate interest (GDPR Art. 6(1)(f))
   for processing contact data of sole traders and liberal professionals when it concerns them only in that capacity;
   Art. 19.1 covers company staff contact data. GDPR Art. 14 requires informing people whose data was not obtained from
   them, at the latest at the first communication (**VERIFY** exact timing wording with counsel).
4. **Previews built with a real business's name are sensitive.** They must stay private, be clearly labelled as a
   proposal from the agency, and never be published or hosted on a look-alike domain.
5. **Recommended go-to-market adjustment (for the user to decide):** use phone, postal mail or in-person visits to offer
   a free website diagnosis; send the diagnosis and preview by email **only after the prospect asks for it** (recorded
   consent). This keeps the expensive T2 preview for prospects who opted in.

## 2. Threat model

| # | Threat | Vector | Impact | Controls |
|---|---|---|---|---|
| T1 | Prompt injection | Instructions hidden in prospect websites, search results, documents, replies | Agent misuses tools, leaks data, writes false evidence | Untrusted content wrapped as data; agents with untrusted input have no `X-EXT`, no secrets, no cross-lead access; schema validation; literal-snippet check; URL allowlisting of outputs; adversarial eval suite (≥ 50 pages) gates releases |
| T2 | SSRF | Fetcher asked to load internal addresses via links/redirects/DNS rebinding | Access to metadata endpoints or internal services | Block private, loopback, link-local, CGNAT, multicast and cloud-metadata ranges (IPv4+IPv6); resolve and pin IP per connection; re-check every redirect (≤ 3); scheme allowlist `https`, `http`; ports 80/443 only; fetcher runs in its own network namespace without route to internal services |
| T3 | Malicious web content in the browser | Exploits against headless Chromium during audits | Container compromise | Playwright/Chromium kept current; sandboxed container, non-root, read-only root FS, no credentials, downloads disabled, one browser context per site, hard time/memory limits, container recycled per batch |
| T4 | Supply-chain compromise | Malicious/compromised npm or PyPI packages, install scripts | Code execution in build/QA or control plane | Dependency admission policy (§4); lockfiles with integrity hashes; install scripts disabled unless reviewed; minimum release age; OSV scanning; SBOM; builds in offline containers from a vetted image |
| T5 | Secret leakage | Keys in prompts, logs, artifacts, generated sites | Account abuse, spend | Secrets only in the gateway process; never in prompts/events/artifacts; log redaction; per-environment keys with provider-side spend limits; no real keys in dev/test |
| T6 | Cost exhaustion | Runaway loops, injection-induced calls, retries | Unbounded spend | Reserve-then-settle budgets at every scope; deny-not-truncate; max turns/tool calls per task; kill switch |
| T7 | Data exfiltration via outputs | Agent embeds data/URLs into a generated site or draft | Leak of other leads' data | Per-lead data scoping; manifest URL rules; drafts reviewed before use; previews contain no other lead's data (test) |
| T8 | Dashboard XSS / CSRF | Captured third-party content rendered in UI; forged approval requests | Account takeover, unauthorized approvals | Render captures as text; previews in sandboxed iframes on a separate origin; strict CSP; CSRF tokens; re-authentication for approvals; four-eyes option |
| T9 | Approval spoofing / replay | Approval reused for a different action | Unauthorized outreach/publication | Approval bound to `exact_action_sha256`, expiry, single execution via idempotency key |
| T10 | Spreadsheet formula injection | Website text exported to CSV/XLSX | Code execution / data exfiltration in spreadsheet apps | Prefix dangerous leading characters; export as text |
| T11 | Unauthorized security testing allegation | Diagnosis behaves like a scanner | Legal exposure, reputational harm | Passive-only rules (§6.2); no vulnerability findings at all |
| T12 | Misleading sales claims | Overstated diagnosis, fabricated facts in previews | Unfair-practice complaints, reputational harm | Measurement date/tool on every claim; `sales_safe` flag; claim detector in copy; no testimonials/ratings generated |
| T13 | Event/ledger tampering | Insider or bug alters history | Loss of auditability | Append-only event store (DB permissions); optional hash chain; daily ledger reconciliation |

## 3. Agent and runtime security controls

- No `SYS` tools exist (shell, filesystem, code execution, arbitrary HTTP, package installation). This rules out by design
  framework built-ins such as AgentScope 2.0's `Bash`/`Write`/`Edit`/`Read`/`Glob`/`Grep` tools — any framework
  integration must register **zero** built-in tools (spike acceptance test, see roadmap).
- Workers run in containers: non-root, read-only root filesystem, `no-new-privileges`, all Linux capabilities dropped,
  seccomp default profile, CPU/memory/pids/time limits, ephemeral writable scratch only.
- Egress per worker type: Fetcher → public internet via SSRF guard; Auditor → same as Fetcher; Astro builder → **no
  network** (dependencies baked into the image); QA runner → loopback only (serves the built site locally); Agent runner
  → LLM endpoint only, through the gateway.
- Test suites run with a socket lock (OI `offline_lock` pattern): any network attempt fails the test.
- Kill switch: one flag stops task leasing and makes the gateway deny everything except reads of internal state.

## 4. Supply-chain and dependency admission policy

A dependency (direct or framework) is admitted only when all apply:

1. **Licence** in the allowlist: MIT, Apache-2.0, BSD-2/3-Clause, ISC, MPL-2.0 (file-level copyleft; used unmodified),
   OFL-1.1 (fonts). LGPL needs a recorded decision; GPL/AGPL/SSPL/proprietary are denied by default.
2. **Maintenance**: a release in the last 12 months, or a written justification (e.g. Lighthouse CI fails this: last
   release 2025-06-25).
3. **Advisories**: no unpatched high/critical advisory at the pinned version (OSV/GitHub advisories checked at admission
   and continuously in CI).
4. **Transitive tree reviewed**: size, install scripts, native binaries, network calls at install or import time.
5. **Pinned** exact versions in a lockfile with integrity hashes; upgrades via reviewed PRs; a minimum release age (e.g.
   14 days) for non-security upgrades.
6. **First execution in a sandbox** with egress blocked to observe behaviour (no unexpected network calls, telemetry or
   file writes outside scratch).
7. **SBOM** (CycloneDX) generated per build; licence and advisory report attached to releases.

The Phase 0 assessment of candidate dependencies is in [decisions.md § Dependency assessment](decisions.md#dependency-assessment).

## 5. Personal data protection (GDPR + LOPDGDD)

| Topic | Rule in WAOS |
|---|---|
| Role | The agency is the controller for prospect data; LLM, hosting and email providers are processors (DPA required before use). |
| Data scope | Business-level data first. Personal data limited to business contact details **published by the business itself** (name of a sole trader as business name, business phone/email/address). No private social profiles, no family data, no home addresses unless it is the published business address, no special categories, no inferred traits about individuals. |
| Legal basis | Legitimate interest (GDPR 6(1)(f)), relying on LOPDGDD Art. 19 presumptions where applicable, with a written Legitimate Interest Assessment (LIA) per campaign stored as `lia_id`. Consent where LSSI requires it. |
| Transparency | Privacy notice published on the agency site; Art. 14 information (identity, purpose, legal basis, data source, categories, recipients, retention, rights incl. objection, AEPD complaint) given at the latest at first contact — scripted into call scripts and letters by the compliance template store (**VERIFY** with counsel). |
| Objection / erasure | Any objection → immediate suppression across all channels; erasure → delete personal data, keep salted hash in suppression list to honour it. |
| Retention (proposal) | Non-qualified leads: personal fields deleted after 6 months; contacted-but-not-converted: 12 months after last contact; suppression hashes: indefinite; raw page captures: 90 days (evidence keeps snippet + hash); clients: per contract/legal duties. Enforced by scheduled jobs that emit events. |
| Records | Record of processing activities (Art. 30); DPIA **screening** before M4 (systematic evaluation/scoring of sole traders may meet DPIA criteria — decide with counsel). |
| Minimization in AI | Prompts carry only the fields a task needs; provider zero-/limited-retention options used when available; no personal data in eval sets unless synthetic. |
| International transfers | Processor locations and transfer mechanisms recorded per provider before onboarding (**UNKNOWN** until providers chosen). |
| Breach | Incident runbook; AEPD notification within 72 h where required (GDPR Art. 33). |
| Automated decisions | Scoring only prioritizes sales effort; it has no legal or similarly significant effect on the business. Documented as not Art. 22 processing (**VERIFY**). |

## 6. Public data collection rules

### 6.1 Sources

| Source type | Status | Notes |
|---|---|---|
| Business's own website | Allowed (passive, robots.txt honoured) | Primary first-party evidence |
| Official registries / open data (e.g. BORME, municipal open data) | Allowed after per-source reuse-terms check | **VERIFY** reuse conditions per source |
| Opportunity Intelligence import | Allowed | Through the OI bridge; carries OI provenance |
| Operator CSV import | Allowed | Operator attests source legality per file |
| Business directories | **Blocked until** ToS and database-right review per directory | Many prohibit scraping; EU sui generis database right |
| Google Maps / Places | **Not for scraping.** API use only if ToS allow the use case | Places terms: `place_id` may be stored indefinitely; lat/lng cacheable ≤ 30 days; other Places content must not be pre-fetched/cached/stored; no display on a non-Google map (Google Maps Platform Service Specific Terms; Places policies — checked 2026-10-19). A lead database built from Places content is therefore not compatible with those terms |
| Social networks | Blocked | ToS and personal-data risk |
| Paid data brokers | Blocked by default | Contact data from brokers conflicts with the contact-evidence rules; provider data never `KNOWN` |

Text-and-data-mining reservations (EU DSM Directive Art. 4; Spanish transposition — **VERIFY**) and robots.txt are
honoured; a site that disallows our user agent is recorded as `BLOCKED_BY_ROBOTS` and only its existence is used.

### 6.2 Passive-diagnosis rules (no security testing)

- Only GET/HEAD of URLs linked from the site or listed in its sitemap; ≤ 20 pages per site per diagnosis.
- ≤ 1 request every 2 s per domain; ≤ 1 concurrent browser per domain; back off on 429/503.
- Identifying User-Agent with a URL explaining the crawler and an opt-out contact.
- No form submission, login, search-box fuzzing, directory guessing, port scanning, vulnerability or version probing,
  CAPTCHA solving, or paywall/robots circumvention.
- No security findings are recorded or reported (outdated CMS, exposed files, etc.).

## 7. Asset provenance and intellectual property

| Rule | Detail |
|---|---|
| Every asset has an `AssetRecord` | Origin, licence snapshot hash, usage scope, AI-generation metadata |
| Third-party content from the prospect's site | Facts may be restated in new words; text is not copied verbatim into production copy; their photos/logo may appear **only** in private previews as `PREVIEW_ONLY` and require written client permission before production |
| Stock assets | Only from libraries whose licence allows commercial web use; licence terms snapshotted |
| Fonts | Self-hosted, OFL or commercially licensed; no runtime third-party font CDN (avoids IP transfer to third parties; cf. LG München I, 3 O 17493/20, 2022) |
| AI-generated images | Allowed only for abstract/illustrative imagery; never realistic depictions of real people, the client's team, premises or "completed works"; recorded with model and prompt hash. EU AI Act Art. 50 transparency obligations apply since 2 August 2026 (deep-fake disclosure; machine-readable marking duties fall on generative-system providers — **VERIFY** scope and the reported marking grace period to 2 December 2026 on EUR-Lex) |
| Fabricated social proof | Testimonials, reviews, ratings, awards, certifications, client logos, project counts and years in business are never generated; they appear only with evidence or client-provided proof |

## 8. External APIs and accounts

Onboarding checklist per provider (recorded as an approval of type `DATA_SOURCE_ENABLE`):
ToS allow the use case · DPA signed (if personal data) · data location and retention / zero-retention options · pricing
known and recorded in `pricing.v1.json` · rate limits known · provider-side spend cap configured · key scoped to minimum
permissions · separate keys per environment · rotation schedule · usage/balance endpoint for reconciliation (if any).
Phase 0 created **no** accounts and used **no** keys.

## 9. Contact eligibility and outbound communications

### 9.1 Channel policy (deterministic, `policy/contact.v1.json`)

| Channel | Default status | Conditions to become usable | Basis |
|---|---|---|---|
| Email | `NOT_ELIGIBLE` | Valid `ConsentRecord` covering email, or documented prior contractual relationship | LSSI Art. 21 |
| SMS / WhatsApp / social DM / web contact form | `NOT_ELIGIBLE` | Same as email (treated as equivalent electronic communication until counsel decides otherwise — **VERIFY**) | LSSI Art. 21 |
| Phone | `ELIGIBLE_WITH_CHECKS` | Number published by the business itself (`KNOWN`, `OFFICIAL`); not suppressed; campaign LIA on file; exclusion-list (Robinson) check for the phone channel within policy window; no automated dialling; call script with Art. 14 information and objection handling; calling-hours policy | LGTel Art. 66.1.b; AEPD Circular 1/2023; LOPDGDD Art. 23 (**VERIFY**) |
| Postal mail | `ELIGIBLE_WITH_CHECKS` | Business address `KNOWN`; not suppressed; LIA; exclusion-list check for postal; Art. 14 information in the letter | GDPR 6(1)(f); LOPDGDD Arts. 19, 23 |
| In person | `ELIGIBLE_WITH_CHECKS` | Visit to business premises during opening hours; Art. 14 leaflet; records created only after the visit | GDPR |

The status is computed by code from evidence and records; agents and humans cannot override it except by adding the
missing record (e.g. a consent record with its evidence), which is itself audited.

### 9.2 Mandatory content of any communication

Sender identity (agency legal entity — **UNKNOWN**, user to provide), how the data was obtained, purpose, how to object
(simple, free, effective immediately), privacy-notice link; diagnosis claims stated as "lab test on <date> with
<tool, version>"; no fear or urgency tactics; no statement that the business breaks a law; no impersonation; preview
disclaimer.

### 9.3 Sending

The system has **no automatic sending capability**. A human sends or calls; the approval service only records
the approved exact text/script and, after sending, the human logs the outcome. If automated email sending is ever
added (consented contacts only), it is an `X-EXT` action executed once per approval.

## 10. Human approvals catalogue

| Action | Approval type | Approvers | Expiry |
|---|---|---|---|
| Start a campaign (sources, queries, quotas, budget) | `CAMPAIGN_PLAN` | 1 | 7 days |
| Build a T2 preview | `PREVIEW_T2` | 1 | 7 days |
| Contact a lead (message/script/letter, channel) | `OUTREACH` | 1 (2 if configured) | 7 days |
| Raise any budget cap | `BUDGET_RAISE` | budget owner | 48 h |
| Make any site/preview publicly reachable | `PUBLISH` | operator + client sign-off record | 7 days |
| Any other external write | `EXTERNAL_WRITE` | 1 | 24 h |
| Enable a data source / external API | `DATA_SOURCE_ENABLE` | admin | — |
| Standing destination (e.g. one Google Sheet) | `EXTERNAL_DESTINATION` | admin | revocable |

## 11. Previews and publication

- Previews are private: authenticated access or signed, expiring URLs (≤ 30 days); `X-Robots-Tag: noindex, nofollow` and
  `robots.txt` disallow; no analytics; forms disabled; no third-party requests.
- Visible banner on every page: "Propuesta conceptual preparada por <agencia>. No es la web oficial de <negocio>."
- Never hosted on a domain containing or resembling the business's name; no domain registrations for prospects.
- Takedown on request within one business day; preview deleted when the lead is suppressed or after expiry.
- Production publication requires: client sign-off, production quality profile pass, legal pages (LSSI Art. 10 legal
  notice, privacy policy, cookie policy only if cookies), asset licences verified, `PUBLISH` approval.

## 12. Logging, audit and incidents

All approvals, transitions, tool calls, costs and policy decisions are events; access to prompts and raw captures is
role-restricted and itself logged. Incident runbook: kill switch → revoke keys → preserve events → assess personal-data
impact → notify where required → post-mortem as an ADR.

## 13. Open legal questions for counsel (before M4/M8)

1. Do web contact forms, WhatsApp Business and LinkedIn messages count as "equivalent electronic means" under LSSI Art. 21?
2. Exact obligations for B2B phone prospecting to companies vs sole traders under LGTel Art. 66 and Circular 1/2023.
3. Which exclusion lists must be checked per channel and how often.
4. Is showing a private preview that uses a prospect's name/logo acceptable, and under what conditions?
5. Is a DPIA required for this processing?
6. Reuse conditions for BORME and municipal open-data sources.
7. Wording and timing of Art. 14 information for phone and postal first contact.
8. AI Act Art. 50 applicability to AI-assisted copy and imagery on client sites.
