# Web Agency OS — Data Contracts

Revision: Phase 0, corrected after the Phase 0 review ([phase0-review.md](phase0-review.md)). Date: 2026-10-19.
Status: **design only.** These definitions become versioned JSON Schemas (`contracts/waos.<name>.v1.schema.json`) when
M1 implementation is authorized (PD-01). Examples use synthetic data and `.example` domains.

Status labels and `P-xx` parameters: [decisions.md](decisions.md#status-labels).

Conventions:

- IDs are ULIDs with a type prefix (`lead_`, `ev_`, `fnd_`, `msr_`, `scr_`, `apr_`, `led_`, `sup_`, `evt_`, `cmp_`).
- Timestamps are RFC 3339 UTC. Money is integer cents with a currency code.
- Every record carries `schema_version`, `data_mode` (`SYNTHETIC | TEST_FIXTURE | REAL`) and `created_at`.
  **M1 rejects `REAL`.**
- `UNKNOWN` is always a valid, explicit value; it is never coerced to false, zero or empty.

## 0. Which contracts belong to M1

| Contract | M1 | Section |
|---|---|---|
| `Lead` | ✔ | §5 |
| `EvidenceRecord` | ✔ | §3 |
| `Finding` (with its `Measurement` reference) | ✔ | §4 |
| `ScoreRecord` (three-layer assessment) | ✔ | §6 |
| `Event` | ✔ | §7 |
| `ApprovalRequest` | ✔ | §8 |
| `LedgerEntry` (+ budget configuration) | ✔ | §9 |
| `SuppressionEntry` | ✔ | §10 |
| CSV export format | ✔ | §11 |
| Contact point, consent, dossier, strategy, creative brief, asset, site manifest, QA report, sales package | later | §12 |

Versioned configuration files used by M1 (data, not records): `campaign` fixture (§2), `rules/scoring.v1.json`,
`rules/impact_rules.v1.json`, `rules/evidence_strength.v1.json`, `rules/transitions.v1.json`
([architecture § 5.4](architecture.md#54-lead-state-machine)), `pricing.v1.json`, `retention.v1.json` (values P-22,
HYPOTHESIS).

## 1. Shared vocabulary (aligned with OI)

| Concept | Values | Origin |
|---|---|---|
| `claim_status` | `KNOWN · INFERRED · ESTIMATED · UNKNOWN · CONFLICTING` | OI `common.v1`, verbatim |
| `source_class` | `OFFICIAL · PUBLIC_REGISTRY · MEASUREMENT · PROFESSIONAL_DIRECTORY · SECTOR_SOURCE · OTHER_VERIFIABLE · HUMAN_REVIEW · UNVERIFIED · NOT_FOUND` | OI + extensions |
| `evidence_origin` | `FIRST_PARTY_WEB · MEASUREMENT · PUBLIC_REGISTRY · DIRECTORY · OPERATOR_IMPORT · HUMAN_REVIEW · FIXTURE · OTHER_VERIFIABLE` | OI (provider values dropped) + `FIXTURE` for M1 |
| `evidence_strength` | `HIGH · MEDIUM · LOW · UNKNOWN` — derived by rules, never declared | OI `evidence_strength.v1` |
| `identity_status` | `KNOWN_MATCH · KNOWN_MISMATCH · AMBIGUOUS · UNKNOWN` | OI |

Mapping to OI `evidence_input.v1` is defined but only used when the OI bridge is approved (deferred, D-001):
`OFFICIAL → OFFICIAL/FIRST_PARTY_WEB`; `MEASUREMENT`, `PUBLIC_REGISTRY → OTHER_VERIFIABLE` (lossy); unmappable values
are rejected, never coerced.

## 2. Campaign (configuration)

| Field | Notes |
|---|---|
| `campaign_id`, `name` | |
| `area` | `{ municipalities[], districts[], postal_codes[] }`. Real area **PENDING** (PD-12; H-6 is only a hypothesis). |
| `categories[]` | Taxonomy ids. The initial hypothesis (construction/renovation, installers, specialized workshops, other local services) is not a decision. |
| `category_value_bands` | `{ category_id: NONE \| LOW \| MEDIUM \| HIGH \| UNKNOWN }`. **No real values are set** (P-14, PD-17). For real data every band is `UNKNOWN` until the user provides them; M1 fixtures use explicitly synthetic bands. |
| `budget` | §9 |
| `scoring_rules_version` | |
| `data_mode` | `SYNTHETIC` in M1 |

## 3. EvidenceRecord

`waos.evidence.v1`

| Field | Req. | Notes |
|---|---|---|
| `evidence_id` | ✔ | |
| `subject` | ✔ | `{ lead_id, entity_key, person_ref: null }` |
| `field` | ✔ | From the field registry, e.g. `business.address`, `business.phone`, `site.has_tel_link`, `site.lcp_ms` |
| `value` | ✔ | `null` only with `UNKNOWN` / `NOT_FOUND` |
| `claim_status`, `source_class`, `evidence_origin` | ✔ | |
| `method` | ✔ | `{ tool, tool_version, procedure_id, params_hash }`; in M1 `tool = "fixture"` |
| `source_url` | if `KNOWN` | |
| `capture_sha256` | if `KNOWN` and from a web capture | Kept even after the raw capture is deleted |
| `capture_available` | ✔ | `true` while the raw capture is retained; `false` afterwards → the evidence can no longer be re-verified (fixes E6) |
| `snippet` | if `KNOWN` and textual | Literal substring of the sanitized capture text (checked when the capture is available) |
| `retrieved_at` | ✔ | |
| `dated_on` | | Date stated by the content itself |
| `confidence` | ✔ | Producer's declaration; informative only |
| `strength` | derived | Computed by rules; any declared value is ignored |
| `proposed_by` | ✔ | `worker@version`, `fixture`, or `human:<id>` (agents only in later phases) |
| `personal_data` | ✔ | `NONE · BUSINESS_CONTACT · OTHER` |
| `retention_until` | if `personal_data ≠ NONE` | From `retention.v1.json` (P-22, HYPOTHESIS, legal review required) |
| `erased` | ✔ | `true` after erasure: `value`, `snippet` set to `null`; ids and hashes remain |
| `data_mode` | ✔ | |

Invariants (enforced in code; tested in M1):

1. `KNOWN` requires `source_url` and, for textual facts, a non-empty `snippet` found literally in the capture text;
   for measurements, a `method`.
2. A fact seen only in a search-result snippet is never `KNOWN`.
3. An inference is never `KNOWN`.
4. Emails and phone numbers must appear literally in the snippet; pattern-built values are rejected.
5. `NOT_FOUND` ⇒ `value = null`, `claim_status = UNKNOWN`.
6. Two incompatible `KNOWN` values for one field ⇒ the field resolves to `CONFLICTING`; neither is chosen.
7. Data from a paid data broker can never be `KNOWN`.

## 4. Measurements and findings (layer 1: technical evidence)

`waos.measurement.v1`: `measurement_id, lead_id, url, procedure_id, tool, tool_version, environment{…}, runs[],
aggregate {median, spread, n}, captured_at, status`. In M1 measurements come from fixtures.

`waos.finding.v1`: `finding_id, lead_id, code, technical_severity (CRITICAL | MAJOR | MINOR | INFO), claim_status,
measured_value, threshold_param (P-xx), rule_version, evidence_ids[], measurement_ids[], sales_safe, detected_at`.
A finding states a **technical fact only**; its acquisition impact is a separate hypothesis (§6.2).

### 4.1 Finding catalogue v1 (thresholds are provisional parameters)

All real-site checks are passive (security § 5.2) and out of scope until M2b is approved.

| Code | Technical problem | How measured | Threshold | Severity | Sales-safe |
|---|---|---|---|---|---|
| `NO_SITE` | No website found | No owned domain in listed sources | P-08; one source → `INFERRED` | CRITICAL | ◐ phrase as "no hemos encontrado web" |
| `SITE_DOWN` | Unreachable | DNS failure / 5xx / timeout | P-07 | CRITICAL | ✔ |
| `NO_HTTPS` | No HTTPS or no redirect to HTTPS | Request to `http://`; TLS | any | MAJOR | ✔ |
| `TLS_INVALID` | Invalid certificate | TLS verification | any | MAJOR | ✔ |
| `NOT_MOBILE_READY` | Not usable on mobile | No viewport meta, horizontal overflow at 360 px, tap targets | any | MAJOR | ✔ |
| `SLOW_MOBILE` | Poor lab performance | Lighthouse mobile, median (P-01) | P-03 | MAJOR | ✔ as "prueba de laboratorio, fecha, herramienta" |
| `LAYOUT_SHIFT` | Unstable layout | Lighthouse CLS median | P-04 | MINOR | ✔ |
| `NO_MOBILE_CONTACT_PATH` | No phone/contact action early on mobile | Browser at 360×800 | P-09 | MAJOR | ✔ |
| `A11Y_SERIOUS` | Serious barriers detected automatically | axe-core, WCAG A/AA rules | ≥ 1 critical/serious | MINOR | ◐ never "incumple la ley" |
| `SEO_BASICS_MISSING` | Missing title/description/H1, accidental `noindex` | HTML inspection | any on home | MINOR | ✔ |
| `NO_LOCAL_SIGNALS` | No address/area or LocalBusiness data | HTML + JSON-LD | both absent | INFO | ✔ |
| `BROKEN_INTERNAL_LINKS` | Broken internal links | Crawl within P-10 | P-05 | MINOR | ✔ |
| `MIXED_CONTENT` | Insecure subresources | Network log | any | MINOR | ✔ |
| `STALE_CONTENT_SIGNAL` | Possibly outdated | Copyright year / latest dated content | P-06 | INFO | ✖ (`INFERRED`) |
| `TRACKING_BEFORE_CONSENT` | Trackers before consent | First-load cookies/requests | any | INFO | ✖ (legal topic; human only) |

"Outdated design" is subjective and is not a finding. Security observations (outdated CMS versions, exposed files) are
out of scope.

### 4.2 Basic site facts (deterministic extraction; fixes E2)

Alongside findings, the diagnosis stage extracts — without any LLM — facts needed by the gates: `tel:` and `mailto:`
links, JSON-LD `LocalBusiness` fields (name, address, telephone, `@type`), visible address blocks, dated content.
Structured data and links on the business's own site → `OFFICIAL`, `KNOWN` with snippet; heuristic text extraction →
`INFERRED`. A human reviewer may confirm any of them as `HUMAN_REVIEW` evidence. In M1 these facts come from fixtures.

## 5. Lead

`waos.lead.v1`

| Field | Notes |
|---|---|
| `lead_id`, `campaign_id`, `entity_key` | |
| `state`, `state_version` | Written only by the workflow engine; `state_version` for optimistic concurrency |
| `business` | `{ name, category_id, municipality?, postal_code?, website_url?, domain? }`, each resolved value with its `evidence_id` |
| `identity` | `{ status, evidence_ids[] }` |
| `latest_score_id` | |
| `purchase_intent` | `UNKNOWN` by default. Later phases may set another value **only** from a human-recorded interaction with the prospect. **M1 schema: constant `UNKNOWN`.** No automated component may write it (D-021). |
| `suppressed` | bool, mirrors §10 |
| `on_hold_from` | previous state when `ON_HOLD` |
| `data_mode`, timestamps | |

Contactability (channel eligibility) is not part of the lead score (D-023) and is out of scope in this phase.

## 6. Three-layer assessment: technical evidence, acquisition impact, commercial opportunity

### 6.1 Layers

| Layer | Component(s) | Meaning | Must not be read as |
|---|---|---|---|
| 1 Technical evidence | `TG` technical gap | How severe the measured technical problems are | Need, value or intent |
| 2 Acquisition impact | `IM` impact | Hypothesis that the problems affect how customers find or contact the business (`INFERRED`) | A measured business loss |
| 3 Commercial opportunity | gates, `BV`, `AC`, `CX` → bucket | Whether the lead deserves a human's review for a possible proposal | Probability of purchase, purchase intent |

`purchase_intent` is outside the assessment (§5).

### 6.2 Acquisition-impact rules (`rules/impact_rules.v1.json`) — HYPOTHESIS H-4

| Impact hypothesis | Finding codes |
|---|---|
| `HIGH` | `NO_SITE`, `SITE_DOWN`, `NO_MOBILE_CONTACT_PATH`, `NOT_MOBILE_READY`, `NO_HTTPS`, `TLS_INVALID` |
| `MEDIUM` | `SLOW_MOBILE`, `SEO_BASICS_MISSING`, `NO_LOCAL_SIGNALS`, `BROKEN_INTERNAL_LINKS` |
| `LOW` | `LAYOUT_SHIFT`, `MIXED_CONTENT`, `A11Y_SERIOUS` (low for *sales prioritization* only; accessibility still matters in what we build) |
| not used | `STALE_CONTENT_SIGNAL`, `TRACKING_BEFORE_CONSENT` |

This table is a hypothesis to be validated in pilot P1; changing it changes `rules_hash`.

### 6.3 Gates (any `FAIL` with `KNOWN` evidence → `DISQUALIFIED`; any `UNKNOWN` → `PENDING`)

| Gate | PASS when | Acceptable evidence |
|---|---|---|
| `G_IDENTITY` | `identity.status = KNOWN_MATCH` | Identity evaluation |
| `G_GEO` | Address or stated service area within the campaign area | `OFFICIAL` (own site, structured data) or `HUMAN_REVIEW` |
| `G_CATEGORY` | Category in campaign categories | `OFFICIAL` services statement or `HUMAN_REVIEW`; an `INFERRED` classification is not enough |
| `G_ACTIVE` | Activity dated within P-12 | `KNOWN` dated content, `PUBLIC_REGISTRY` or `HUMAN_REVIEW` |
| `G_NOT_EXCLUDED` | Not suppressed, not an existing client, not a competitor agency | Internal lists (`KNOWN`) |

Gates often stay `UNKNOWN` until a human reviews them. That is intended: the lead stays `PENDING` rather than being
promoted on inference.

### 6.4 Buckets (HYPOTHESIS)

Components (integer levels; `UNKNOWN` inputs contribute 0 to the floor and the level maximum to the ceiling):

| Component | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| `TG` technical gap (layer 1) | no finding | ≥ 1 MINOR | ≥ 1 MAJOR | any CRITICAL or ≥ 2 MAJOR |
| `IM` acquisition impact (layer 2) | no impact hypothesis | max `LOW` | max `MEDIUM` | max `HIGH` |
| `BV` business value band | `NONE` | `LOW` | `MEDIUM` | `HIGH` (band `UNKNOWN` → floor 0, ceiling 3) |
| `AC` activity signals | none | 1 | 2 | ≥ 3 distinct `KNOWN` signals |

Only findings with `KNOWN` status count toward floors; `INFERRED` findings count toward ceilings only.

Contraindications `CX` (each with a claim status): `RECENT_REDESIGN`, `AGENCY_MAINTAINED` (e.g. a "designed by"
credit), `FRANCHISE_OR_CHAIN`, `LARGE_COMPANY`, `OTHER_PRIMARY_CHANNEL`.

| Bucket | Rule (first match wins; thresholds are P-13) |
|---|---|
| `DISQUALIFIED` | any gate `FAIL` |
| `PENDING` | any gate `UNKNOWN` |
| `REVIEW_PRIORITY` | `IM.floor ≥ 2` and `BV.floor ≥ 2` and `AC.floor ≥ 1` and no `KNOWN` contraindication and confidence ∈ {`STRONG`, `MODERATE`} |
| `WATCH` | `IM.floor ≥ 1` or `TG.floor ≥ 2` (including leads capped by a `KNOWN` contraindication) |
| `LOW` | otherwise |

`TG` never enters the `REVIEW_PRIORITY` rule: technical severity alone cannot promote a lead. Ordering within a bucket
uses `opportunity_points = IM + BV + AC` (floor, then ceiling); equal keys remain tied; no tie-breaks on name, size or
discovery order. `REVIEW_PRIORITY` means "worth a human's review", and moving to `SHORTLISTED` still requires a human
shortlist approval.

### 6.5 Confidence band (HYPOTHESIS)

Definition is provisional parameter P-32.

| Band | Rule |
|---|---|
| `STRONG` | All gates `PASS` with evidence strength `HIGH`, and the finding that sets `IM` is `KNOWN` |
| `MODERATE` | All gates `PASS`; supporting evidence includes `MEDIUM` strength |
| `LOW_ONLY` | Any supporting evidence of `LOW` strength |
| `NONE` | Otherwise |

### 6.6 ScoreRecord (`waos.score.v1`)

`score_id, lead_id, scoring_version, rules_hash (SHA-256 of the canonical rules files used), computed_at,
gates[] {gate_id, result PASS|FAIL|UNKNOWN, evidence_ids[]},
layer1 {TG {floor, ceiling, finding_ids[]}},
layer2 {IM {floor, ceiling, impact_rule_ids[]}},
layer3 {BV, AC {floor, ceiling, evidence_ids[]}, contraindications[] {code, claim_status, evidence_ids[]},
opportunity_points {floor, ceiling}, confidence_band, bucket},
explanation[] (rule ids fired, in order), calibrated: false,
disclaimer: "priority for human review; not a probability or indication of purchase intent"`.

Same inputs + same rules ⇒ identical record (excluding `score_id` and `computed_at`).

## 7. Event

`waos.event.v1`

| Field | Notes |
|---|---|
| `seq` | Integer, strictly increasing; defines order |
| `event_id` | ULID |
| `ts` | From the injected clock |
| `type` | See list below |
| `actor` | `{ kind: SYSTEM \| HUMAN \| AGENT, id }` (no agents in M1); written by the component that acted |
| `lead_id`, `subject_refs[]` | Identifiers only |
| `causation_id`, `correlation_id` | Event or command that caused this one; run id |
| `payload` | Type-specific; ids, hashes, versions, outcomes, reasons — **no personal-data values** (D-024) |
| `prev_hash` | If the hash chain is adopted (PD-05) |
| `schema_version` | |

M1 event types: `import.completed · import.rejected · evidence.recorded · evidence.rejected · evidence.erased ·
finding.recorded · score.computed · state.transitioned · state.transition_denied · approval.requested ·
approval.decided · approval.executed · approval.rejected · tool.call_completed · tool.call_denied · budget.changed ·
suppression.recorded · retention.purged · export.created · export.refused · system.kill_switch · integrity.checked`.

## 8. ApprovalRequest

`waos.approval.v1`

| Field | Notes |
|---|---|
| `approval_id`, `type` | M1 types: `SHORTLIST`, `BUDGET_CHANGE`. Later types (`PREVIEW_T2`, `OUTREACH`, `PUBLISH`, `EXTERNAL_WRITE`, `DATA_SOURCE_ENABLE`, `EXTERNAL_DESTINATION`) are defined but have no executor in this phase |
| `action` | `{ kind, params }` — the exact action |
| `action_sha256` | SHA-256 of the canonical JSON of `action` (UTF-8, sorted keys, no insignificant whitespace) |
| `requested_by`, `requested_at`, `expires_at` | Expiry from P-21 (HYPOTHESIS) |
| `decision` | `{ decision: APPROVED \| REJECTED, by: human:<id>, at, comment }` |
| `status` | `PENDING · APPROVED · REJECTED · EXPIRED · EXECUTED` |
| `executed_at`, `execution_count` | `execution_count ∈ {0, 1}` |

An approval authorizes an execution only if **all** hold: status `APPROVED`; not expired; never executed; the decider is
`HUMAN`; the type matches the action kind; and the SHA-256 of the action being executed equals `action_sha256`.
In M1, operator identity is self-declared on the CLI (architecture § 6.3; PD-07).

## 9. LedgerEntry and budget

`waos.ledger_entry.v1`: `entry_id, ts, run_id, tool, operation, input_sha256, pricing_version, unit_price_cents
(null = unknown), reserved_cents, actual_cents, status (OK | DENIED | ERROR), deny_reason (PAID_CALLS_DISABLED |
UNKNOWN_PRICE | NO_BUDGET | CAP_EXCEEDED | TOOL_NOT_ALLOWED), budget_remaining_cents`.

Budget configuration: `{ global_cap_cents, per_run_cap_cents, source: USER_PARAMETER, approved_by }`. M1 values are
synthetic. The paid-call switch is two independent settings (code constant and configuration), both `false` in M1.

## 10. SuppressionEntry and data-protection fields

`waos.suppression.v1`: `suppression_id, identifiers_sha256[] (salted hashes of normalized domain, phone, email),
reason (OPT_OUT | OBJECTION | ERASURE | POLICY), created_at, source_ref`. Salted hashes are pseudonymous data and may
still be personal data — the retention and legal treatment of suppression entries are **PENDING** legal review (P-22).

Effects (tested in M1 with synthetic data): a suppressed lead moves to `SUPPRESSED` (terminal); its personal-data
evidence values are erased; exports omit its contact columns; future imports matching a suppressed hash are rejected.

## 11. CSV export format (M1)

File name includes the data mode (e.g. `leads_SYNTHETIC_<timestamp>.csv`); UTF-8; RFC 4180 quoting of every field.

| Column | Source | Notes |
|---|---|---|
| `lead_id`, `campaign_id` | Lead | |
| `business_name`, `category`, `municipality`, `website` | Lead/evidence | Exported as text |
| `business_phone` | evidence | Blank when suppressed or erased |
| `state` | Lead | |
| `priority_for_review` | ScoreRecord bucket | Header deliberately not "interest" or "intent" |
| `opportunity_points_floor` / `_ceiling` | ScoreRecord | |
| `TG_floor`, `IM_floor`, `BV_floor`, `AC_floor` | ScoreRecord | |
| `confidence_band`, `contraindications`, `unknown_gates` | ScoreRecord | |
| `top_findings`, `impact_hypotheses` | Findings / impact rules | Impact column labelled as hypothesis |
| `purchase_intent` | Lead | Always `UNKNOWN` in M1 |
| `suppressed`, `data_mode`, `scoring_version`, `rules_hash`, `exported_at` | | |

Safety rules:

1. **Formula injection:** any cell whose first character is `=`, `+`, `-`, `@`, tab, carriage return or line feed —
   or their full-width forms — is prefixed with a single quote `'`.
2. All fields quoted; embedded quotes doubled; embedded newlines preserved inside quotes.
3. Export refuses records with `data_mode = REAL` in M1 (`export.refused`).
4. Each export writes `export.created` with the file's SHA-256, row count and column list (no cell values).
5. Excel-specific concerns (BOM, delimiter locale) are **PENDING**; no spreadsheet application is assumed.

## 12. Later-phase contracts (not in M1)

Defined in Phase 0 drafts and retained as design intent; each will be re-specified when its phase is approved:

- **ContactPoint** — channel, literal value, evidence (must contain the value), purpose, contactability status computed
  by policy (`ELIGIBLE · ELIGIBLE_WITH_CHECKS · NOT_ELIGIBLE · UNKNOWN`), checks performed. Depends on legal review.
- **ConsentRecord** — subject, channels, purpose, method, evidence, text presented, obtained by, withdrawn at.
- **InteractionRecord** — human-recorded contact outcome; the only source that may change `purchase_intent`.
- **ResearchDossier**, **WebsiteStrategy**, **CreativeBrief** — every factual sentence references evidence.
- **AssetRecord** — origin (`LICENSED_STOCK · OWN_CREATED · AI_GENERATED · CLIENT_PROVIDED · THIRD_PARTY_UNLICENSED`),
  licence snapshot hash, `usage_scope` (`PREVIEW_ONLY · PRODUCTION_ALLOWED`), people/work depiction flags.
- **WebsiteProjectManifest** — the only input to the Astro builder: typed components and props, claims linked to
  evidence or explicit placeholders, no raw HTML/scripts/external URLs, preview privacy settings.
- **QAReport**, **SalesPackage** — gate results with tool versions; drafts with notices and claim references.
