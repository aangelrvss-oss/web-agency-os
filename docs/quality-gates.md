# Web Agency OS — Astro Website Factory and Quality Gates

Revision: Phase 0, corrected after the Phase 0 review ([phase0-review.md](phase0-review.md)). Date: 2026-10-19.
Status: **design for later phases.** The factory (M6a/M6b) and any preview generation are out of scope until approved
(D-020). Numeric targets are provisional parameters (P-26, P-27, HYPOTHESIS) — chosen as goals, not demonstrated; the
hand-built reference site (M6a) is where they are first tested (H-5).

Three things are measured separately and never substituted for one another:

| Dimension | Measured by | A pass means | A pass does **not** mean |
|---|---|---|---|
| Visual quality ("premium") | Human design review against a written rubric (§1.7) | Meets the agency's design standard | Accessible, fast, or converting |
| Accessibility | axe-core automated checks + manual WCAG 2.2 AA checklist (§3) | No automatically detectable violations; manual checks done | Full conformance. Automation finds only part of the issues (a Deque study reports ~57 % of issues by volume — REPORTED). **No AAA claim is ever made**; the target is WCAG 2.2 AA |
| Performance / technical SEO | Lighthouse lab runs (median), HTML and structured-data checks | Lab metrics and technical basics within targets | Real-user experience or search rankings |
| Conversion orientation | Presence and placement of conversion components (§1.3); later, measured conversions (PD-23) | The page offers clear, accessible paths to contact | That visitors will contact the business |

## 1. Website factory

### 1.1 Shape (target)

```
factory/
  packages/tokens/        design tokens (colour roles, type scale, spacing, radii, shadows, motion durations/easings)
  packages/components/    Astro components, no client JS by default; a JSON Schema for each component's props
  themes/                 one theme first (from the reference site); more only after it is proven
  starters/               category starters: page/section presets and the JSON-LD type
  manifest/               site manifest schema + validator
  build/                  manifest → content files → `astro build` (static output) → artifact (sha256)
  qa/                     Playwright + Lighthouse + axe-core + HTML/links/structured-data checks, gate evaluator
```

- Static HTML/CSS; JavaScript only for components that need it (e.g. an accessible mobile menu).
- Agents never write code; they choose components and props. Components are written and reviewed by people, with their
  own visual and accessibility tests.
- Reproducible builds: same manifest + same lockfile → same output hash.
- Build container without network.
- **Order:** first a reference website built by hand (M6a), then extract tokens and components from it (M6b). The quality
  ceiling of the factory is the quality of that component library and of the photography, not the architecture.

### 1.2 Design system rules (measurable proxies)

| Area | Rule |
|---|---|
| Typography | ≤ 2 families; modular scale from tokens; readable body size and line length; self-hosted subset fonts |
| Spacing & layout | Token spacing only; consistent section rhythm; no ad-hoc pixel values in components |
| Colour | Palette roles from tokens; text/background pairs meet WCAG AA contrast (checked in code); one accent |
| Imagery | Sufficient source resolution per slot; art-directed crops per breakpoint; responsive `srcset`; width/height always set |
| Hierarchy | One primary call to action per screen of content; contact action reachable in the first mobile screen for service businesses |
| Third parties | None by default: no analytics, no external fonts, no embedded maps (static image + link), no chat widgets |
| Content | Every factual claim traceable to evidence or shown through the visible `Placeholder` component in previews |

### 1.3 Conversion components (required catalogue)

The component library must include, designed and tested in M6a:

- Sticky mobile call/contact bar (accessible, not covering content or focus).
- Hero with the offer, location served and primary action in the first screen.
- Quote-request form (production only; disabled in previews; backend and privacy notice decided later).
- Service list and service-area section (real areas from evidence).
- Before/after or project gallery — only with client-provided, licensed photos.
- Trust block — only verifiable items (memberships, guarantees offered by the client, real reviews with permission and
  source); never generated.
- Clear contact section with name, phone, address and hours from evidence.

How conversions are measured on production sites (cookieless analytics or consent-based) is PENDING (PD-23).

### 1.4 Scroll animations

- Animate only `transform` and `opacity`; durations and easings from tokens (P-26).
- **Never animate the LCP element or above-the-fold content**; their final state is visible on first paint.
- Content is fully visible without JavaScript; animation is an enhancement.
- Under `prefers-reduced-motion: reduce`, all non-essential motion is disabled.
- No scroll-jacking, no large-area parallax, no autoplay video with sound, nothing flashing more than 3 times per second.
- CSS scroll-driven animations are used only where supported, with an `IntersectionObserver` fallback; **browser support
  is PENDING verification** before M6a.
- Gates: Lighthouse is run with animations enabled; CLS must stay within target; a reduced-motion run must show no
  animation.

### 1.5 Photography and genericness risk

Stock imagery for trades tends to look generic, and a prospect's own photos need permission. Previews may therefore look
less "premium" than the final site. Mitigations: an art-direction guide in the reference site, a curated licensed library,
explicit placeholders for client photos, and human design review. This is a known risk, not a solved problem.

### 1.6 Image pipeline safety

Astro had a reported critical advisory in image optimization (GHSA-26w7-cxv4-gfx2, AVIF via Sharp/libheif, reported fixed
in 7.2.8 — REPORTED). Policy: Astro at or above the fixed version, confirmed at admission; image inputs restricted to
JPEG/PNG/WebP from the asset store; no images fetched from the internet at build time.

### 1.7 Design rubric

Criteria, each scored 1–5 by the human reviewer (PD-25), with an optional advisory pre-score by an agent in later phases:

typographic hierarchy and readability · spacing rhythm and consistency · colour harmony and contrast · imagery quality
and relevance · clarity of the offer in the first screen (what, where, how to contact) · clarity of the conversion path ·
credibility signals (only real ones) · mobile ergonomics (thumb reach, sticky action) · motion restraint · distinctiveness
and brand fit (does not look like a template) · copy quality in Spanish (specific, concise, no unverifiable claims) ·
consistency across pages.

Pass thresholds are P-27 (HYPOTHESIS); they are confirmed or changed after scoring the reference site.

## 2. Quality profiles

All values are provisional targets (P-26, HYPOTHESIS).

| Gate | Preview profile (T1/T2) | Production profile (T3) |
|---|---|---|
| Build | `astro check` clean; build succeeds; output hash recorded | same |
| Lighthouse runs (P-02) | 3, median | 5, median |
| Lighthouse Performance (mobile) | ≥ 85 | ≥ 90 |
| Lighthouse Accessibility score | ≥ 95 (informative; axe is the gate) | ≥ 95 |
| Lighthouse Best Practices | ≥ 90 | ≥ 95 |
| Lighthouse SEO | excluded (previews are `noindex` on purpose) | ≥ 95 |
| LCP (lab, mobile) | ≤ 3.0 s | ≤ 2.5 s |
| CLS (with animations on) | ≤ 0.1 | ≤ 0.1 |
| TBT (lab proxy for responsiveness) | ≤ 300 ms | ≤ 200 ms |
| JavaScript per page (compressed) | ≤ 50 KB | ≤ 30 KB |
| Home page transfer (mobile) | ≤ 1.5 MB | ≤ 1.0 MB |
| Fonts | ≤ 4 files, ≤ 150 KB | same |
| axe-core | 0 violations for `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa` on every page at 360×800, 768×1024, 1440×900 and with the menu open | same + `best-practice` findings reviewed |
| Manual accessibility checklist (§3) | not required | required, signed by the reviewer |
| HTML validity | 0 errors | 0 errors |
| Links | 0 broken internal | 0 broken internal; external checked |
| Layout (Playwright at 360/768/1280/1920) | no horizontal overflow; nothing outside the viewport; no overlapping text; images loaded; 0 console errors; 0 failed requests | same + visual diff against the approved baseline on revisions |
| Conversion components | primary contact action in the first mobile screen | §1.3 catalogue applied as specified by the strategy |
| Network | 0 requests to non-local origins | only allowlisted origins |
| Cookies on first load | 0 | 0 unless an approved consent design exists |
| Content | placeholders only via `Placeholder`; facts with evidence refs | 0 placeholders or template tokens; facts with evidence or client proof |
| Forbidden content | no generated testimonials, ratings, awards, statistics, prices outside the price table | same |
| Technical SEO | title/description; one `h1`; `lang="es"`; canonical; valid JSON-LD for the chosen schema.org type | + sitemap, robots allow, Open Graph, contact data consistent with evidence |
| Preview safety | `noindex`, disclaimer banner, private access, expiry | n/a |
| Legal pages | n/a | per counsel (security L18) |
| Assets | `usage_scope` compatible with previews | all `PRODUCTION_ALLOWED`; licences verified |
| Design review (§1.7) | P-27 preview threshold | P-27 production threshold |

Retry policy (P-18): a failing gate returns its report to the assembler; limited regenerations; then human review.
Lighthouse variance: if a median falls within P-31 of a threshold, one full re-measurement; thresholds are never lowered
per project.

## 3. Manual accessibility checklist (production)

Target WCAG 2.2 AA, on home, one service page and the contact page, desktop and mobile: keyboard-only navigation and
focus order · visible focus not obscured by sticky elements (2.4.7, 2.4.11) · target size ≥ 24×24 CSS px (2.5.8) · reflow
at 320 CSS px (1.4.10) · text spacing (1.4.12) · contrast of text over images · meaningful alternative text · headings
and landmarks · page language · reduced-motion behaviour · consistent help (3.2.6) · form labels, errors and
instructions (3.3.x) · screen-reader smoke test.

Allowed public statement: "Diseñada siguiendo las pautas WCAG 2.2 nivel AA; revisión automática y manual realizada el
<fecha>." Not allowed: "accesible al 100 %", "cumple AAA", or legal-compliance claims. European Accessibility Act
applicability is assessed per client (security L13, PENDING).

## 4. Diagnosis measurement standards (prospect sites; M2a/M2b)

- Three layers are reported separately: technical finding (layer 1), acquisition-impact hypothesis (layer 2), opportunity
  bucket (layer 3) — see [data-contracts § 6](data-contracts.md#6-three-layer-assessment-technical-evidence-acquisition-impact-commercial-opportunity).
  A technical measurement is never presented as a business loss or as interest in buying.
- Tool versions pinned and recorded in every measurement; Lighthouse mobile, simulated throttling, median of P-01 runs,
  one run per CPU core at a time; runner location recorded.
- A finding is reported only if its threshold is exceeded with margin, or confirmed on a different day for `SITE_DOWN`.
- Sales-facing statements include date and tool and describe a lab test, not users' experience.
- Base rates per finding are measured in M2b; a finding present on almost every site discriminates poorly (H-7).
- Human validation uses two labels per site: correctness of the findings, and "would you propose a new website?".

## 5. Agent output quality gates (later phases)

Schema validity after at most one repair; zero factual statements without evidence or finding references; every `KNOWN`
snippet found literally in its capture; zero tool-policy violations on the prompt-injection suite; cost within the task
envelope. Thresholds P-29 (HYPOTHESIS).

## 6. Tooling (later phases; versions REPORTED, admission review required)

| Tool | Use | Note |
|---|---|---|
| Playwright | Layout, functional, screenshot and network checks; drives axe | REPORTED latest 1.64.x; CVE-2025-59288 reported fixed in 1.55.1 |
| Lighthouse via Node API | Performance, best-practice and SEO audits with our own median-of-N runner | Lighthouse CI not adopted (D-012; REPORTED low activity) |
| axe-core + `@axe-core/playwright` | Automated accessibility checks | MPL-2.0 (REPORTED), used unmodified |
| HTML validator, JSON-LD checker | Validation | Not assessed |
