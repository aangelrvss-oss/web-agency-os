# Web Agency OS — Data Contracts (Phase 0)

Status: **proposal, not implemented**. Date: 2026-10-19. These definitions become versioned JSON Schemas
(`contracts/waos.<name>.v1.schema.json`) in milestone M1. Field lists here are normative for M1; examples are illustrative
and use synthetic data (`.example` domains).

Conventions:

- IDs are ULIDs with a type prefix: `cmp_`, `lead_`, `ev_`, `cap_`, `msr_`, `fnd_`, `scr_`, `ctc_`, `cns_`, `dos_`,
  `stg_`, `cbr_`, `ast_`, `prj_`, `qa_`, `sp_`, `apr_`, `tc_`, `rsv_`, `evt_`.
- Timestamps are RFC 3339 UTC. Money is integer cents (`eur_cents`) with currency.
- Every record carries `schema_version`, `data_mode` (`SYNTHETIC | TEST_FIXTURE | REAL`, from OI) and `created_at`.
- `UNKNOWN` is always a valid, explicit value. It is never coerced to false, zero or empty.

## 1. Shared vocabulary (aligned with OI)

| Concept | Values | Origin |
|---|---|---|
| `claim_status` | `KNOWN · INFERRED · ESTIMATED · UNKNOWN · CONFLICTING` | OI `common.v1`, verbatim |
| `source_class` | `OFFICIAL · PUBLIC_REGISTRY · MEASUREMENT · PROFESSIONAL_DIRECTORY · SECTOR_SOURCE · OTHER_VERIFIABLE · HUMAN_REVIEW · UNVERIFIED · NOT_FOUND` | OI `common.v1` + extensions |
| `evidence_origin` | `FIRST_PARTY_WEB · MEASUREMENT · PUBLIC_REGISTRY · DIRECTORY · OI_IMPORT · HUMAN_REVIEW · OTHER_VERIFIABLE` | OI `evidence_input.v1` (Apollo values dropped) |
| `evidence_strength` | `HIGH · MEDIUM · LOW · UNKNOWN` — **derived by rules, never declared** | OI `evidence_strength.v1` |
| `identity_status` | `KNOWN_MATCH · KNOWN_MISMATCH · AMBIGUOUS · UNKNOWN` | OI evaluators |
| `eligibility` | `ELIGIBLE · PENDING_EVIDENCE · UNKNOWN · NOT_ELIGIBLE` | OI D010 / qualification |

### 1.1 Mapping to OI `evidence_input.v1`

| WAOS `source_class` | OI `source_class` | OI `evidence_origin` | Note |
|---|---|---|---|
| `OFFICIAL` | `OFFICIAL` | `FIRST_PARTY_WEB` | Business's own site, read at origin |
| `MEASUREMENT` | `OTHER_VERIFIABLE` | `OTHER_VERIFIABLE` | Lossy: WAOS keeps `method` in `note`; OI has no measurement class |
| `PUBLIC_REGISTRY` | `OTHER_VERIFIABLE` | `OTHER_VERIFIABLE` | OI `core/` uses `PUBLIC_OFFICIAL`; to reconcile in OI |
| `HUMAN_REVIEW` | (export `source_class` of underlying evidence) | `HUMAN_REVIEW` | |
| others | same name | `OTHER_VERIFIABLE` | |

Exports are rejected (not coerced) when a value has no mapping. `strength` is not exported: OI re-derives it.

## 2. Campaign

| Field | Type | Notes |
|---|---|---|
| `campaign_id` | id | |
| `name` | string | |
| `area` | `{ municipalities[], districts[], postal_codes[] }` | **UNKNOWN today**: "southeast Madrid" must be defined by the user. Proposal to confirm: Madrid districts Puente de Vallecas, Villa de Vallecas, Moratalaz, Vicálvaro; municipalities Rivas-Vaciamadrid, Arganda del Rey and neighbours |
| `categories[]` | taxonomy ids | Initial hypothesis: construction/renovation, installers (plumbing, electrical, HVAC, solar, aluminium/PVC joinery, locksmiths), specialized workshops (mechanics, body shops, motorcycles, tyres), other local services |
| `budget` | `Budget` (§11) | Required (`BUDGET_REQUIRED` otherwise) |
| `quotas` | `{ max_discovered, max_diagnosed, max_t1, max_t2_per_week }` | |
| `sources[]` | source ids | Only sources with completed ToS/licence review |
| `scoring_rules_version` | string | |
| `status` | `DRAFT · AWAITING_APPROVAL · ACTIVE · PAUSED · CLOSED` | |
| `approval_id` | id | Campaign-plan approval |

## 3. EvidenceRecord

`waos.evidence.v1` — superset of OI `evidence_input.v1`.

| Field | Type | Req. | Notes |
|---|---|---|---|
| `evidence_id` | id | ✔ | |
| `subject` | `{ lead_id, entity_key, person_ref: null }` | ✔ | `entity_key` = registrable domain, or `name|postcode` normalized when no domain. `person_ref` stays null except for business contact persons published by the business itself |
| `field` | string (field registry) | ✔ | e.g. `business.services`, `business.phone`, `business.address`, `site.https`, `site.lcp_ms` |
| `value` | scalar or small object | ✔ | `null` allowed only with `UNKNOWN` / `NOT_FOUND` |
| `claim_status` | enum | ✔ | |
| `source_class` | enum | ✔ | |
| `evidence_origin` | enum | ✔ | |
| `method` | `{ tool, tool_version, procedure_id, params_hash }` | ✔ | e.g. `{lighthouse, 13.5.0, LH-MOBILE-3RUN, …}` or `{fetcher, 1.0.0, PAGE-TEXT, …}` |
| `source_url` | url \| null | KNOWN | |
| `capture_id` | sha256 | KNOWN (web) | Raw capture in the artifact store |
| `snippet` | string | KNOWN (textual) | Must be a literal substring of the sanitized capture text (checked) |
| `snippet_locator` | `{ selector?, char_start, char_end }` | | |
| `retrieved_at` | datetime | ✔ | |
| `dated_on` | date \| null | | Date stated by the content itself |
| `confidence` | `HIGH · MEDIUM · LOW · UNKNOWN` | ✔ | Producer's declaration; informative only |
| `strength` | enum | derived | Computed by `evidence_strength` rules; producer value ignored |
| `corroborated_by[]` | evidence ids | | |
| `proposed_by` | `agent@version` \| `worker@version` \| `human:<id>` | ✔ | |
| `reviewed_by` | human id \| null | | |
| `personal_data` | `NONE · BUSINESS_CONTACT · OTHER` | ✔ | Drives retention and access |
| `retention_until` | date | ✔ | Set by policy (see security doc) |
| `data_mode` | enum | ✔ | |

Invariants (enforced in code, from OI `core/project_opportunity.validate` and contact checks):

1. `KNOWN` requires `source_url`, `capture_id` (for web) and a non-empty `snippet` (for textual facts) or a `method`
   (for measurements).
2. A fact seen only in a search-result snippet is never `KNOWN` (`seen_in = search_snippet` → max `UNVERIFIED`).
3. An inference is never `KNOWN`. Classifier outputs are always `INFERRED`.
4. Emails and phone numbers must appear literally in the snippet; pattern-built contact data is rejected.
5. `NOT_FOUND` ⇒ `value = null` and `claim_status = UNKNOWN` (OI rule).
6. Two incompatible `KNOWN` values for the same field ⇒ both remain; the field resolves to `CONFLICTING` (never pick one).
7. Data from a paid data broker can never be `KNOWN` (OI rule for provider data).

Example:

```json
{
  "schema_version": "waos.evidence.v1",
  "evidence_id": "ev_01JABCDEF0SYNTH",
  "subject": {"lead_id": "lead_01JSYNTH", "entity_key": "reformas-ejemplo.example", "person_ref": null},
  "field": "business.services",
  "value": "reformas integrales de cocinas y baños",
  "claim_status": "KNOWN",
  "source_class": "OFFICIAL",
  "evidence_origin": "FIRST_PARTY_WEB",
  "method": {"tool": "fetcher", "tool_version": "1.0.0", "procedure_id": "PAGE-TEXT", "params_hash": "a1b2…"},
  "source_url": "https://reformas-ejemplo.example/servicios",
  "capture_id": "sha256:9f2c…",
  "snippet": "Realizamos reformas integrales de cocinas y baños en Vallecas",
  "retrieved_at": "2026-10-19T09:12:00Z",
  "dated_on": null,
  "confidence": "HIGH",
  "proposed_by": "business_researcher@1.0.0",
  "personal_data": "NONE",
  "retention_until": "2027-10-19",
  "data_mode": "SYNTHETIC"
}
```

## 4. Measurements and findings

### 4.1 Measurement (`waos.measurement.v1`)

`measurement_id, lead_id, url, final_url, procedure_id, tool, tool_version, environment {form_factor, throttling,
cpu_slowdown, user_agent, location_of_runner}, runs[] {run_index, metrics{…}, artifact_ref}, aggregate {median{…},
stdev{…}, n}, captured_at, status (OK | PARTIAL | FAILED), error_code`.

Lighthouse-based procedures always run ≥ 3 times and store the median and spread; single runs are never used for findings.

### 4.2 Finding (`waos.finding.v1`)

`finding_id, lead_id, code, severity (CRITICAL | MAJOR | MINOR | INFO), claim_status, measured_value, threshold,
rule_version, evidence_ids[], measurement_ids[], scored (bool), sales_safe (bool), detected_at, expires_at`.

`sales_safe=false` findings may inform internal scoring but must not be mentioned to the prospect without human review.

### 4.3 Finding catalogue v1 (diagnosis of prospect sites)

All checks are **passive**: GET/HEAD of publicly linked pages a normal visitor would load, ≤ 20 pages per site, robots.txt
honoured, no forms submitted, no logins, no vulnerability probing (see security doc).

| Code | Problem | How measured | Threshold (v1, tunable) | Severity | Scored | Sales-safe |
|---|---|---|---|---|---|---|
| `NO_SITE` | No website found | No URL in official listings/registry + site search returns no owned domain | Two independent sources → `KNOWN`; one → `INFERRED` | CRITICAL | ✔ | ✔ (phrased as "no hemos encontrado web") |
| `SITE_DOWN` | Unreachable | DNS failure / 5xx / timeout | 3 attempts over ≥ 24 h | CRITICAL | ✔ | ✔ |
| `NO_HTTPS` | No HTTPS or HTTP not redirected | Request to `http://`; TLS handshake | No valid HTTPS, or no redirect | MAJOR | ✔ | ✔ |
| `TLS_INVALID` | Expired/mismatched certificate | TLS verification | Any failure | MAJOR | ✔ | ✔ |
| `NOT_MOBILE_READY` | Not usable on mobile | No `meta viewport`, or horizontal overflow at 360 px, or tap targets below Lighthouse audit | Any | MAJOR | ✔ | ✔ |
| `SLOW_MOBILE` | Poor lab performance | Lighthouse mobile, median of 3 | Performance < 50 **or** LCP > 4.0 s | MAJOR | ✔ | ✔ (with "prueba de laboratorio, fecha, herramienta") |
| `LAYOUT_SHIFT` | Unstable layout | Lighthouse CLS median | > 0.25 | MINOR | ✔ | ✔ |
| `NO_MOBILE_CONTACT_PATH` | No phone/contact action reachable on mobile home | Playwright at 360×800: no `tel:` link, contact link or form within first 2 screens | Absent | MAJOR | ✔ | ✔ |
| `A11Y_SERIOUS` | Serious accessibility barriers detected automatically | axe-core, WCAG A/AA tags, home + contact | ≥ 1 `critical`/`serious` violation | MINOR | ✔ | ◐ (phrase as "barreras detectadas automáticamente", never "incumple la ley") |
| `SEO_BASICS_MISSING` | Missing title/meta description/H1, or accidental `noindex` | HTML inspection | Any on home | MINOR | ✔ | ✔ |
| `NO_LOCAL_SIGNALS` | No address/area served or no LocalBusiness structured data | HTML + JSON-LD parse | Both absent | INFO | ✔ | ✔ |
| `BROKEN_INTERNAL_LINKS` | Broken links | Crawl ≤ 20 pages | ≥ 3 internal 4xx | MINOR | ✔ | ✔ |
| `MIXED_CONTENT` | Insecure subresources | Browser console/network | Any | MINOR | ✔ | ✔ |
| `STALE_CONTENT_SIGNAL` | Possibly outdated | Copyright year / latest dated post | ≥ 3 years old | INFO | ✖ | ✖ (`INFERRED`, weak) |
| `TRACKING_BEFORE_CONSENT` | Non-essential cookies/trackers before consent | Cookies/requests on first load, no interaction | Any | INFO | ✖ | ✖ (legal topic; human review only) |
| `OUTDATED_DESIGN` | Subjective visual age | — | — | — | ✖ | ✖ — **not a finding**; may appear only as a human note |

Security-related observations (e.g. outdated CMS versions) are **out of scope**: they invite unauthorized-testing
concerns and are not used for scoring or sales.

## 5. Lead

`waos.lead.v1`

| Field | Type | Notes |
|---|---|---|
| `lead_id`, `campaign_id` | id | |
| `state` | lead state (architecture §4.3) | Written only by the workflow engine |
| `entity_key` | string | |
| `business` | `{ name, legal_name?, category_id, subcategory_ids[], address?, municipality?, district?, postal_code?, website_url?, domain? }` | Each populated field also exists as evidence; the lead stores the current resolved value + `evidence_id` |
| `identity` | `{ status, method, evidence_ids[] }` | |
| `discovery` | `[{ source_id, query_id, retrieved_at, rank, external_ref? }]` | External refs only where licence permits storage (e.g. Google `place_id` is storable; other Places content is not cacheable) |
| `tier_reached` | `T0 · T1 · T2 · T3` | |
| `latest_score_id`, `latest_diagnosis_id`, `dossier_id?` | ids | |
| `owner` | user id \| null | |
| `suppressed` | bool | Mirrors suppression service |
| `next_action` | `{ action, due_at, reason }` | From rules (OI `next_action` design) |
| `cost_to_date` | money | Sum of settled ledger entries |
| `data_mode`, timestamps | | |

## 6. Scoring

### 6.1 ScoreRecord (`waos.score.v1`)

`score_id, lead_id, scoring_version, rules_hash, computed_at, gates[] {gate_id, result PASS|FAIL|UNKNOWN, evidence_ids[]},
eligibility, components {W|V|A|R: {floor, ceiling, level_rule_id, evidence_ids[]}}, total {floor, ceiling},
confidence_band (STRONG | MODERATE | LOW_ONLY | NONE), bucket (PRIORITY | WATCH | LOW | PENDING | DISQUALIFIED),
explanation[] (rule ids fired, in order), calibrated: false`.

### 6.2 Scoring rules v1 (rules-as-data, `rules/scoring.v1.json`)

Design taken from OI: hard gates with `UNKNOWN ≠ PASS`; score as an interval (floor = demonstrated, ceiling = possible
if unknowns resolve favourably, as in D010); no tie-breaks on name, size or discovery order; `calibrated=false` until
calibrated against human labels.

**Gates** (any `FAIL` with `KNOWN` evidence → `DISQUALIFIED`; any `UNKNOWN` → `PENDING_EVIDENCE`):

| Gate | PASS when |
|---|---|
| `G_IDENTITY` | `identity.status = KNOWN_MATCH` |
| `G_GEO` | Business address or declared service area within campaign area (`KNOWN`) |
| `G_CATEGORY` | Category in campaign categories (`INFERRED` acceptable for gate PASS only if confirmed by an `OFFICIAL` services claim) |
| `G_ACTIVE` | Evidence of activity dated within 12 months (dated content, registry status, recent listing update) |
| `G_NOT_EXCLUDED` | Not suppressed, not an existing client, not a franchise/branch whose website is centrally managed, not a competitor agency |

**Components** (integer levels; each level has an explicit rule):

| Component | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| **W** website gap (from findings) | No scored finding | ≥ 1 MINOR | ≥ 1 MAJOR | `NO_SITE` or `SITE_DOWN`, or ≥ 2 MAJOR including `NOT_MOBILE_READY` or `NO_MOBILE_CONTACT_PATH` |
| **V** commercial value (category band, user-set) | Category band `NONE` | `LOW` | `MEDIUM` | `HIGH` |
| **A** activity / demand | No signal | 1 signal | 2 signals | ≥ 3 signals (e.g. multiple service lines stated, service-area pages, recent dated projects, hiring notice) |
| **R** reachability | No eligible channel | Only in-person | Postal eligible (with checks) | Phone eligible (with checks) or valid consent record |

`UNKNOWN` inputs contribute 0 to the floor and the component maximum to the ceiling.

**Buckets**:

| Bucket | Rule (first match wins) |
|---|---|
| `DISQUALIFIED` | Any gate `FAIL` |
| `PENDING` | Any gate `UNKNOWN` |
| `PRIORITY` | `W.floor ≥ 2` and `V.floor ≥ 2` and `R.floor ≥ 2` and confidence band ∈ {STRONG, MODERATE} |
| `WATCH` | `W.floor ≥ 1` and `V.floor ≥ 1` |
| `LOW` | otherwise |

Within a bucket, order by `total.floor` descending, then `total.ceiling`; equal keys remain tied (competition ranking).
Category value bands (`V`) are user assumptions to be confirmed; for example, renovation and HVAC/solar installers are
proposed `HIGH`, mechanics `MEDIUM` (ASSUMPTION, not evidence).

## 7. Contact and consent

### 7.1 ContactPoint (`waos.contact_point.v1`)

`contact_id, lead_id, channel (PHONE | POSTAL | EMAIL | WEB_FORM | SOCIAL | IN_PERSON), value (literal, as published),
purpose (GENERAL | SALES | SUPPORT | PERSONAL | UNKNOWN), owner_type (BUSINESS | NAMED_PERSON), evidence_ids[]
(must contain the literal value), source_class, eligibility {status: ELIGIBLE | ELIGIBLE_WITH_CHECKS | NOT_ELIGIBLE |
UNKNOWN, reasons[], checks {robinson_checked_at?, robinson_result?, lia_id?, consent_id?, suppression_checked_at}},
policy_version`.

Eligibility is computed by the Policy engine (see security doc §9); agents never set it.

### 7.2 ConsentRecord (`waos.consent.v1`)

`consent_id, subject {lead_id, contact_id}, channels[], purpose, obtained_at, method (VERBAL_DURING_CALL |
WRITTEN_REPLY | WEB_FORM | IN_PERSON_SIGNED), evidence_ref (notes/recording/form capture), text_presented,
obtained_by (human id), withdrawn_at?`.

### 7.3 SuppressionEntry (`waos.suppression.v1`)

`suppression_id, identifiers_hashed[] (normalized domain, E.164 phone, lower-cased email — salted SHA-256),
reason (OPT_OUT | OBJECTION | ERASURE | POLICY), created_at, source (channel / request ref)`. Kept indefinitely with
minimal data, to honour the objection.

## 8. Research and strategy

- **ResearchDossier** (`waos.dossier.v1`): `dossier_id, lead_id, sections {services, service_area, differentiators,
  proof (certifications, memberships, stated years), brand {logo_capture?, measured_colours[], fonts_detected[]},
  contact, gaps[] (fields UNKNOWN)}` each as lists of `evidence_id`; `summary[] {sentence, evidence_ids[]}`;
  `agent_version`; `cost`.
- **WebsiteStrategy** (`waos.strategy.v1`): `strategy_id, lead_id, tier, primary_conversion (CALL | QUOTE_REQUEST |
  VISIT | OTHER), audience, pages[] {slug, purpose, sections[] {component_id, intent}}, addressed_findings[],
  local_seo_themes[], client_input_needed[], rationale[] {text, refs[]}, constraint_check {page_count_ok, sections_ok}`.
- **CreativeBrief** (`waos.creative_brief.v1`): `theme_id, palette {bg, surface, text, muted, accent, on_accent}
  (hex; AA contrast pairs checked by code), type_pair_id, imagery[] {slot_id, asset_id | query, usage_scope},
  motion {preset_id, intensity 0–2}, logo_treatment (WORDMARK | CLIENT_LOGO_PREVIEW_ONLY)`.

## 9. AssetRecord (provenance)

`waos.asset.v1`

| Field | Notes |
|---|---|
| `asset_id`, `sha256`, `kind` (`IMAGE · FONT · ICON · VIDEO · LOGO · DOCUMENT`) | |
| `origin` | `LICENSED_STOCK · OWN_CREATED · AI_GENERATED · CLIENT_PROVIDED · THIRD_PARTY_UNLICENSED` |
| `license` | `{ licence_id, url, licensor, terms_snapshot_sha256, commercial_use, modification, attribution_required, attribution_text?, expires_at? }` |
| `source_url`, `retrieved_at`, `creator` | |
| `ai_generation` | `{ provider, model, prompt_hash, generated_at, disclosure_required }` when `AI_GENERATED` |
| `usage_scope` | `PREVIEW_ONLY · PRODUCTION_ALLOWED` — `THIRD_PARTY_UNLICENSED` is always `PREVIEW_ONLY` |
| `depicts_real_people` | bool; if true, `model_release_ref` required for production |
| `depicts_client_work` | bool; only `CLIENT_PROVIDED` assets may depict the client's actual work/premises/team |
| `alt_text`, `restrictions[]` | |

## 10. WebsiteProjectManifest

`waos.site_manifest.v1` — the **only** input to the Astro builder. Agents produce it; code validates it.

```json
{
  "schema_version": "waos.site_manifest.v1",
  "project_id": "prj_01JSYNTH",
  "lead_id": "lead_01JSYNTH",
  "tier": "T2",
  "manifest_version": 3,
  "locale": "es-ES",
  "build": {"factory_version": "0.1.0", "astro": "7.4.x (pinned in lockfile)", "component_library": "0.1.0", "theme_id": "solid-craft"},
  "business": {
    "name": {"value": "Reformas Ejemplo", "evidence_ids": ["ev_…"]},
    "phone": {"value": "+34 600 000 000", "evidence_ids": ["ev_…"]},
    "address": {"value": null, "placeholder": true},
    "service_area": {"value": ["Puente de Vallecas", "Rivas-Vaciamadrid"], "evidence_ids": ["ev_…"]}
  },
  "brand": {"palette_ref": "cbr_…", "type_pair_id": "inter-fraunces", "logo": {"treatment": "WORDMARK"}},
  "pages": [
    {
      "slug": "/",
      "seo": {"title": "Reformas de cocinas y baños en Vallecas | Reformas Ejemplo", "description": "…", "jsonld_type": "GeneralContractor"},
      "sections": [
        {"component": "hero.split", "props": {
          "heading": {"text": "Reformas de cocinas y baños en Vallecas", "claims": ["ev_…"]},
          "cta_primary": {"kind": "tel", "contact_ref": "ctc_…"},
          "image": {"asset_id": "ast_…"}
        }},
        {"component": "services.grid", "props": {"items": [{"title": "Cocinas", "body": "…", "claims": ["ev_…"]}]}},
        {"component": "proof.placeholder", "props": {"note": "Fotos de obras reales del cliente"}}
      ]
    }
  ],
  "motion": {"preset_id": "reveal-subtle", "intensity": 1, "respect_reduced_motion": true},
  "analytics": {"enabled": false},
  "forms": {"mode": "DISABLED_IN_PREVIEW"},
  "legal_pages": {"aviso_legal": "REQUIRED_AT_PUBLISH", "privacidad": "REQUIRED_AT_PUBLISH", "cookies": "ONLY_IF_COOKIES"},
  "preview": {"access": "PRIVATE", "noindex": true, "disclaimer_banner": true, "expires_at": "2026-11-18T00:00:00Z"},
  "qa_profile": "preview"
}
```

Validation rules: component ids exist in the catalogue at `component_library` version; props match each component's
schema; every text block with factual content has `claims` or `placeholder: true`; asset `usage_scope` compatible with
tier/profile; no URLs except evidence-backed contact links and internal routes; `analytics.enabled=false` unless a
production consent design exists.

## 11. QA, sales, approvals, budget, ledger

- **QAReport** (`waos.qa_report.v1`): `qa_id, project_id, manifest_sha256, build_sha256, profile (preview | production),
  tool_versions{}, gates[] {gate_id, status PASS|FAIL|WARN|SKIPPED, measured, threshold, artifacts[]}, overall,
  attempt, design_review {reviewer, rubric{…}, decision}?`.
- **SalesPackage** (`waos.sales_package.v1`): `package_id, lead_id, documents[] {kind (DIAGNOSTIC_SUMMARY |
  PROPOSAL_OUTLINE | CALL_SCRIPT | POSTAL_LETTER | EMAIL_DRAFT), content_ref, claim_refs[], notices_included[],
  channel}, offer {tier, price_range_ref}, status (DRAFT | APPROVED | SENT_BY_HUMAN | WITHDRAWN), approval_ids[]`.
- **ApprovalRequest** (`waos.approval.v1`): `approval_id, type (CAMPAIGN_PLAN | PREVIEW_T2 | OUTREACH | BUDGET_RAISE |
  PUBLISH | EXTERNAL_WRITE | DATA_SOURCE_ENABLE | EXTERNAL_DESTINATION), subject_refs[], exact_action {rendered text or
  diff, recipient/channel, URL, amount}, exact_action_sha256, policy_checks[] {check, result}, requested_by,
  requested_at, expires_at, decisions[] {by, at, decision, comment}, required_approvers (1 | 2), execution
  {idempotency_key, executed_at?, result?}`. An approval is valid only for the exact action hash it shows.
- **Budget** (`waos.budget.v1`): `scope (GLOBAL | CAMPAIGN | STAGE | LEAD | TASK), scope_ref, caps {llm_eur_cents,
  paid_api_eur_cents{provider}, credits{provider}, compute_minutes, wall_clock_minutes}, reserve_pct, alerts [50, 80,
  100], source (USER_PARAMETER), approved_by`.
- **BudgetReservation** (`waos.reservation.v1`): `reservation_id, task_id, tool, max_cost, scopes[], status (HELD |
  SETTLED | RELEASED | EXPIRED), actual_cost?, settled_at?`.
- **ToolCallLedger row** — OI `ToolCallLedger` fields (`tool_call_id, run_id, phase, tool, operation, input_hash,
  entity_ids, estimated_cost, actual_cost, credit_before, credit_after, credit_delta, remaining_credit_budget, status,
  error_code, started_at, finished_at, data_origin`) **plus** `agent, agent_version, task_id, reservation_id,
  pricing_version, tokens_in, tokens_out`.
- **Event envelope** — see [architecture § 9.1](architecture.md#91-event-model-minimum).

## 12. Spreadsheet fields (lead export)

Export targets: local CSV/XLSX first (no external write). A Google Sheets sync is optional and requires a standing,
scope-limited approval (see security doc). **Formula-injection rule**: any cell value beginning with `=`, `+`, `-`, `@`,
tab or carriage return is prefixed with `'`; website-derived text is always exported as text.

| # | Column | Type | Source | Notes |
|---|---|---|---|---|
| 1 | `lead_id` | id | Lead | |
| 2 | `campaign` | string | Campaign | |
| 3 | `business_name` | string | evidence | |
| 4 | `category` / `subcategory` | string | taxonomy | |
| 5 | `municipality` / `district` / `postal_code` | string | evidence | |
| 6 | `website` | url | evidence | |
| 7 | `state` | enum | workflow | |
| 8 | `bucket` | enum | ScoreRecord | |
| 9 | `score_floor` / `score_ceiling` | int | ScoreRecord | |
| 10 | `W` / `V` / `A` / `R` (floor) | int | ScoreRecord | |
| 11 | `confidence_band` | enum | ScoreRecord | |
| 12 | `top_findings` | codes | Findings | e.g. `SLOW_MOBILE;NO_HTTPS` |
| 13 | `perf_mobile_median` / `lcp_ms_median` / `cls_median` | number | Measurement | with `measured_at` |
| 14 | `https_ok` / `mobile_ready` | TRUE/FALSE/UNKNOWN | Findings | never blank-as-false |
| 15 | `axe_serious_count` | int | Measurement | |
| 16 | `known_evidence_count` / `unknown_fields` | int / list | Evidence | |
| 17 | `last_diagnosed_at` | date | Measurement | |
| 18 | `tier_reached` | T0–T3 | Lead | |
| 19 | `preview_ref` | id (not a public URL) | Project | |
| 20 | `recommended_channel` | enum | Policy engine | |
| 21 | `eligibility_phone` / `eligibility_postal` / `eligibility_email` | enum | Policy engine | |
| 22 | `robinson_checked_at` | date | ContactPoint | |
| 23 | `consent_id` | id | ConsentRecord | |
| 24 | `outreach_approval_id` | id | Approval | |
| 25 | `last_contact_at` / `next_action` / `next_action_due` | date / string / date | CRM | |
| 26 | `owner` | user | CRM | |
| 27 | `outcome` / `lost_reason` | enum / string | CRM (human) | |
| 28 | `suppressed` | bool | Suppression | suppressed rows exported without contact columns |
| 29 | `cost_to_date_eur` | number | Ledger | |
| 30 | `scoring_version` / `data_mode` | string | ScoreRecord / Lead | |
| 31 | `notes` | string | human | free text, exported as text |
