# Web Agency OS — Astro Website Factory and Quality Gates (Phase 0)

Status: **proposal, not implemented**. Date: 2026-10-19.

Three things are measured separately and never substituted for each other:

| Dimension | Measured by | What a pass means | What it does **not** mean |
|---|---|---|---|
| Visual quality ("premium") | Design rubric scored by a human designer (advisory pre-score by `qa_reviewer`) | Meets the agency's design standard | Accessible, fast or correct |
| Accessibility | axe-core automated checks + manual WCAG 2.2 AA checklist | No automatically detectable violations; manual checks done | Full conformance (automation catches only part of the issues — Deque's own study reports ~57 % of issues by volume; per success criterion the share is lower). **No AAA claim is ever made**; the target is WCAG 2.2 **AA** |
| Performance / technical SEO | Lighthouse (lab, median of N runs), HTML/structured-data checks | Lab metrics and technical basics within budget | Real-user experience (no field data for new sites) or rankings |

## 1. Website factory

### 1.1 Shape

```
factory/
  packages/tokens/        design tokens (colour roles, type scale, spacing 4/8 grid, radii, shadows, motion durations/easings)
  packages/components/    Astro components, zero client JS by default; each has a JSON Schema for its props
  themes/                 3 initial themes (e.g. "solid-craft", "clean-technical", "warm-local") = token sets + component variants
  starters/               category starters (renovation, installer, workshop): page/section presets, copy prompts, JSON-LD type
  manifest/               waos.site_manifest.v1 schema + validator
  build/                  manifest → content collections (JSON) → `astro build` (static output) → artifact (sha256)
  qa/                     Playwright + Lighthouse + axe + HTML/links/structured-data runners, gate evaluator
```

- Output: static HTML/CSS with minimal JS (islands only for components that need it, e.g. an accessible mobile menu).
- Agents never write code: `site_assembler` selects components and props; the builder renders them. New components are
  written and reviewed by humans, with their own visual and accessibility tests.
- Builds are reproducible: same manifest + same factory lockfile → same output hash (tested).
- The build container has no network; dependencies come from a vetted image built from the lockfile.

### 1.2 Design system rules (premium, measurable proxies)

| Area | Rule |
|---|---|
| Typography | ≤ 2 families; modular type scale from tokens; body ≥ 16 px; line length 45–80 characters; self-hosted, subset WOFF2 |
| Spacing & layout | Only token spacing values; consistent section rhythm; max content width tokens; no ad-hoc pixel values in components |
| Colour | Palette roles from tokens; text/background pairs meet WCAG AA contrast (checked in code from the creative brief); one accent |
| Imagery | Minimum source resolution per slot (≥ 2× rendered width); art-directed crops per breakpoint; no upscaling artefacts; responsive `srcset`; width/height attributes always set |
| Hierarchy | One primary CTA per viewport-height of content; phone CTA reachable in the first mobile screen for service businesses |
| Motion | Measured: transform/opacity only; 150–600 ms; easing tokens; triggered on entering the viewport (CSS scroll-driven animations where supported, `IntersectionObserver` fallback); content fully visible without JS; **disabled under `prefers-reduced-motion: reduce`**; no scroll-jacking, no parallax on large areas, no autoplay video with sound, nothing flashing more than 3 times per second |
| Third parties | None by default: no analytics, no external fonts, no embedded maps (static map image + link instead), no chat widgets |
| Content | Every factual claim traceable to evidence or rendered through the visible `Placeholder` component in previews |

### 1.3 Image pipeline safety

Astro's image optimization had a critical remote-code-execution advisory (GHSA-26w7-cxv4-gfx2, AVIF via Sharp/libheif,
fixed in Astro 7.2.8). Factory policy: Astro pinned at ≥ 7.2.8 (latest 7.4.x at admission); image **inputs** restricted
to JPEG/PNG/WebP from the asset store (no AVIF/HEIF inputs, no images fetched from the internet at build time); output
formats AVIF/WebP generated from trusted inputs.

## 2. Quality profiles

| Gate | Preview profile (T1/T2) | Production profile (T3) |
|---|---|---|
| Build | `astro check` clean; build succeeds; output hash recorded | same |
| Lighthouse runs | 3 runs, median | 5 runs, median |
| Lighthouse Performance (mobile) | ≥ 85 | ≥ 90 |
| Lighthouse Accessibility score | ≥ 95 (informative; axe is the gate) | ≥ 95 |
| Lighthouse Best Practices | ≥ 90 | ≥ 95 |
| Lighthouse SEO | **excluded** (preview is `noindex` on purpose, which fails the crawlability audit) | ≥ 95 |
| LCP (lab, mobile) | ≤ 3.0 s | ≤ 2.5 s |
| CLS | ≤ 0.1 | ≤ 0.1 |
| TBT (lab proxy for INP) | ≤ 300 ms | ≤ 200 ms |
| JS shipped per page (compressed) | ≤ 50 KB | ≤ 30 KB |
| Home page total transfer (mobile) | ≤ 1.5 MB | ≤ 1.0 MB |
| Fonts | ≤ 4 files, ≤ 150 KB | same |
| axe-core | 0 violations for tags `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa` on every page, at 360×800, 768×1024, 1440×900, and with the mobile menu open | same + `best-practice` violations reviewed |
| Manual accessibility checklist (§3) | Not required | Required, signed by reviewer |
| HTML validity | 0 errors | 0 errors |
| Internal links | 0 broken | 0 broken; external links checked (HEAD) |
| Layout checks (Playwright, 360/768/1280/1920) | No horizontal overflow; no element outside viewport; no overlapping text boxes; all images loaded; 0 console errors; 0 failed requests | same + visual diff vs approved baseline on revisions |
| Network | 0 requests to non-local origins | Only allowlisted origins (e.g. form backend) |
| Cookies on first load | 0 | 0 unless a consent design is approved |
| Content | Placeholders allowed only via `Placeholder` component; every factual block has evidence refs | 0 placeholders, 0 `TODO`/`lorem`/template tokens; every factual block has evidence or client-provided proof |
| Forbidden content | No generated testimonials, ratings, awards, statistics, prices outside price table | same |
| Technical SEO | Title/description per page; one `h1`; `lang="es"`; canonical; JSON-LD validates against the schema.org type chosen (e.g. `GeneralContractor`, `Plumber`, `Electrician`, `HVACBusiness`, `AutoRepair`) | + `sitemap.xml`, `robots.txt` allow, Open Graph tags, NAP consistent with evidence |
| Preview safety | `noindex` meta + header, disclaimer banner, private access, expiry set | n/a |
| Legal pages | n/a | Legal notice (LSSI Art. 10), privacy policy, cookie policy if any cookies, accessibility statement (recommended) |
| Assets | `usage_scope` compatible with preview | All `PRODUCTION_ALLOWED`; licences verified; attributions rendered |
| Dependencies | Factory lockfile: no high/critical advisories | same + SBOM attached |
| Design review | Rubric ≥ 3.5/5 average (advisory pre-score allowed) | Human designer rubric ≥ 4/5, no criterion < 3 |

Retry policy: a failing gate returns its report to the `site_assembler`; at most 2 regeneration attempts per build;
then `NEEDS_REVIEW`. Lighthouse variance: if a median falls within 3 points of a threshold, one full re-measurement is
allowed and both are recorded; thresholds are never lowered per project.

## 3. Manual accessibility checklist (production)

Target WCAG 2.2 AA. Checked on home, one service page and contact page, desktop and mobile:

keyboard-only navigation and logical focus order · visible focus indicator, not obscured by sticky headers (2.4.7,
2.4.11) · target size ≥ 24×24 CSS px (2.5.8) · reflow at 320 CSS px (1.4.10) · text spacing override (1.4.12) · contrast
of text over images · meaningful alternative text · heading structure and landmarks · page language · reduced-motion
behaviour · consistent help/contact location (3.2.6) · form labels, errors and instructions (3.3.x) when forms exist ·
screen-reader smoke test (NVDA + Firefox or VoiceOver + Safari).

Public statements allowed: "Diseñada siguiendo las pautas WCAG 2.2 nivel AA; revisión automática y manual realizada el
<fecha>." Not allowed: "accesible al 100 %", "cumple AAA", or legal-compliance claims. Note: the European Accessibility
Act (Directive (EU) 2019/882, applicable since 28 June 2025; Spanish transposition **VERIFY**) exempts microenterprises
providing services; whether it applies to a given client is assessed per client, not assumed.

## 4. Diagnosis measurement standards (prospect sites)

Findings about prospects must be reproducible, because they are used in sales conversations:

- Tool versions pinned and recorded in every `Measurement`.
- Lighthouse: mobile form factor, default simulated throttling, 3 runs, median; one Lighthouse run per CPU core at a time
  (concurrency skews results); runner location recorded.
- A finding is reported only if its threshold is exceeded with margin or confirmed by a second measurement on a
  different day for `SITE_DOWN`.
- Every sales-facing statement includes the date and the tool, and describes a lab test, not users' experience.
- Corpus test (M2): a local corpus of ≥ 20 fixture sites with known, labelled defects; each detector must reach
  precision ≥ 0.95 and recall ≥ 0.90 before use on real sites; real-site pilot requires ≥ 90 % human agreement.

## 5. Agent output quality gates

| Gate | Threshold |
|---|---|
| Schema validity | 100 % after ≤ 1 repair; otherwise `FAILED_NEEDS_HUMAN` |
| Evidence anchoring | 0 factual statements without `evidence_id`/`finding_id` (automated claim detector + sampling review) |
| Literal snippet check | 100 % of `KNOWN` textual evidence snippets found in the capture |
| Prompt-injection eval | 0 tool-policy violations, 0 scope escapes on the adversarial suite |
| Cost | Task cost within its envelope; envelopes revised from measured p95 |

## 6. Tooling decisions

| Tool | Use | Note |
|---|---|---|
| Playwright (1.64.x, Apache-2.0) | Layout, functional, screenshot and network checks; drives axe | ≥ 1.55.1 required (CVE-2025-59288 fixed); use the pre-installed browser in sandbox images |
| Lighthouse (13.x, Apache-2.0) via its Node API | Performance, best-practice and SEO audits, with our own median-of-N runner and assertions | Lighthouse CI (`@lhci/cli` 0.15.1, last release 2025-06-25, bundles Lighthouse 12.6.1) **not adopted** for now: stale and lagging Lighthouse 13 |
| axe-core 4.14 + `@axe-core/playwright` 4.14 (MPL-2.0) | Automated accessibility checks | Used unmodified (MPL file-level copyleft not triggered) |
| HTML validator | `html-validate` or Nu validator | **To be assessed** under the admission policy |
| JSON-LD | Validate against schema.org vocabulary with a local checker | To be assessed |

Exact versions are fixed in lockfiles when each milestone starts, after the admission checks in
[security-and-compliance § 4](security-and-compliance.md#4-supply-chain-and-dependency-admission-policy).
