# Synthetic diagnosis corpus (M2a / M2a.1)

Local, fictitious websites (`.example` domains, `+34 000 000 2xx` phones). Each `site.json` states the case's
purpose and its expected results: the 12 check statuses, the site facts, the review bucket and the evaluation status.
Labels were written by Claude (PD-10) **before** running the detectors and are provisional. A label is the result a
correct *static* auditor should give, so a check that cannot be decided from HTML is labelled `UNKNOWN`, not
"probably fine". Labels are never edited to make a run pass; a wrong detector is fixed in code or, if the fix needs a
product decision, kept as a `known_deviation` with its reason.

Evaluation status (scope: the checks whose absence is decidable from static HTML — `SEO_BASICS_MISSING`,
`NO_LOCAL_SIGNALS`, `BROKEN_INTERNAL_LINKS`):
`PROBLEMS_FOUND` = at least one problem confirmed by valid evidence; `NO_PROBLEMS_FOUND` = every in-scope check
completed with no problem (the other 9 checks are still unverified, so this is not a guarantee);
`INSUFFICIENT_EVIDENCE` = an in-scope check is still UNKNOWN.

| Site | Case | Expected evaluation | Expected bucket |
|---|---|---|---|
| s01_good | Correct site (false-positive control) | NO_PROBLEMS_FOUND | LOW |
| s02_bare | Bare page: 4 defects | PROBLEMS_FOUND | PENDING |
| s03_broken_mixed | 3 broken links + http image | PROBLEMS_FOUND | REVIEW_PRIORITY |
| s04_noindex | `noindex` home page | PROBLEMS_FOUND | WATCH |
| s05_ambiguous | http, 2 broken links (below P-05), area only in text | NO_PROBLEMS_FOUND | PENDING |
| s06_blank_title | Whitespace-only title | PROBLEMS_FOUND | PENDING |
| s07_adversarial | Fake phone in comment, hidden instructions, malformed JSON-LD | NO_PROBLEMS_FOUND | PENDING |
| s08_good_variants | Correct site with valid variations (case, unquoted attributes, `@graph`, query/fragment links) | NO_PROBLEMS_FOUND | LOW |
| s09_multi_defect | Six defects at once | PROBLEMS_FOUND | PENDING |
| s10_malformed | Malformed/truncated HTML a browser repairs | NO_PROBLEMS_FOUND | LOW |
| s11_links | Relative, encoded, anchor, PDF and external links; 0 broken | NO_PROBLEMS_FOUND | LOW |
| s12_ambiguous_local | Place name that only contains a campaign municipality as a substring | INSUFFICIENT_EVIDENCE | PENDING |
| s13_contradictory | Two municipalities in JSON-LD; contradictory robots tags | PROBLEMS_FOUND | PENDING |
| s14_no_home | No home page in the capture (absence of evidence) | INSUFFICIENT_EVIDENCE | PENDING |
| s15_crawl_limit | Crawl limit reached; the only broken links are on unseen pages | INSUFFICIENT_EVIDENCE | LOW |
| s16_whatsapp_contact | Contact only by WhatsApp link + quote-form page | NO_PROBLEMS_FOUND | LOW |
| s17_no_contact_channel | Only a search form, a WhatsApp link without number and a look-alike host (added after review) | PROBLEMS_FOUND | PENDING |

## First run of the new labels against procedure `static-html-1.0.0` (before any M2a.1 code change)

Recorded to show which known false positives (FP) and false negatives (FN) the new cases exposed and how each was
resolved. Filled in after the first run; the labels above were not changed.

| Site | First-run result (unchanged code) | Kind | Resolution |
|---|---|---|---|
| s08_good_variants | `NO_LOCAL_SIGNALS` DETECTED; municipality and category missing | FP + missed facts | Fixed: JSON-LD `@graph` is read |
| s10_malformed | `SEO_BASICS_MISSING` DETECTED (H1 never closed); `NO_MOBILE_CONTACT_PATH` DETECTED; phone missing | 2 FP + missed fact | Fixed: `<a>`/`<h1>` closed implicitly like a browser, and at end of document |
| s11_links | `BROKEN_INTERNAL_LINKS` DETECTED (3 percent-encoded file names) | FP | Fixed: paths are percent-decoded before the containment checks (NUL rejected) |
| s12_ambiguous_local | `NO_LOCAL_SIGNALS` NOT_DETECTED and municipality INFERRED as "Villa Sintética Norte" from "Norteña" | wrong pass + wrong fact | Fixed: whole-name match; a substring-only match gives UNKNOWN (`AMBIGUOUS_SIGNAL`) |
| s13_contradictory | `SEO_BASICS_MISSING` NOT_DETECTED (last robots tag won) | FN | Fixed: any `noindex` robots tag counts (most restrictive) |
| s14_no_home | Diagnosis aborted (`index.html missing`) | crash | Fixed: every check UNKNOWN (`HOME_NOT_CAPTURED`), no facts |
| s16_whatsapp_contact | `NO_MOBILE_CONTACT_PATH` DETECTED | FP | First kept as a known deviation; fixed after review (user decision): a WhatsApp click-to-chat link with a number, or a contact form on the home page or a page it links to, is a *possible* contact path (not tested) |
| s17_no_contact_channel | `NO_MOBILE_CONTACT_PATH` UNKNOWN (the site-search form counted as contact) | FN | Fixed: search forms are not contact forms; WhatsApp links need `wa.me`/`api.whatsapp.com`/`whatsapp:` and a number |

s01–s07, s09 and s15 matched their labels on the first run. No known deviation remains.
