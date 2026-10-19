"""M2a: static diagnosis of LOCAL synthetic websites (files on disk). No network, no browser.

Each catalogue check returns DETECTED, NOT_DETECTED or UNKNOWN. NOT_DETECTED is only returned when the check is fully
decidable from the HTML files; anything that needs HTTP, TLS or a browser is UNKNOWN, never a pass.
Results are stored as M1 evidence (site facts + one MEASUREMENT record per check) and findings (DETECTED → KNOWN,
UNKNOWN → UNKNOWN, which only raises score ceilings). Page content is treated as data: it is parsed, never executed.
"""
import json
import os
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from . import evidence as E
from . import schema
from .util import RULES, load_json, new_id, sha256_text

CHECKS = ("SEO_BASICS_MISSING", "NO_LOCAL_SIGNALS", "BROKEN_INTERNAL_LINKS", "MIXED_CONTENT", "NOT_MOBILE_READY",
          "NO_MOBILE_CONTACT_PATH", "NO_HTTPS", "TLS_INVALID", "SITE_DOWN", "SLOW_MOBILE", "LAYOUT_SHIFT", "A11Y_SERIOUS")
RESOURCE_TAGS = {"img", "script", "iframe", "source", "video", "audio", "embed"}
SKIP_TAGS = {"script", "style", "noscript", "template"}


class DiagnosisError(Exception):
    pass


def rules():
    return load_json(os.path.join(RULES, "diagnosis.v1.json"))


class Page(HTMLParser):
    """Collects what the static checks need. Comments are ignored by HTMLParser, so links inside them never count."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self.meta, self.h1, self.links, self.resources = None, {}, [], [], []
        self.jsonld, self.times, self.text, self.forms, self.addresses = [], [], [], 0, 0
        self._stack, self._buf, self._link, self._h1, self._in_title = [], None, None, None, False

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self._buf = []
        if tag in SKIP_TAGS:
            self._stack.append(tag)
        if tag == "title":
            self.title, self._in_title = "", True
        elif tag == "meta" and a.get("name"):
            self.meta[a["name"].lower()] = a.get("content", "")
        elif tag == "h1":
            self._h1 = []
        elif tag == "a" and "href" in a:
            self._link = [a["href"], []]
        elif tag in RESOURCE_TAGS and a.get("src"):
            self.resources.append(a["src"])
        elif tag == "link" and a.get("href") and set(a.get("rel", "").lower().split()) & {"stylesheet", "icon"}:
            self.resources.append(a["href"])
        elif tag == "time" and a.get("datetime"):
            self.times.append(a["datetime"])
        elif tag == "form":
            self.forms += 1
        elif tag == "address":
            self.addresses += 1

    def handle_endtag(self, tag):
        if tag == "script" and self._buf is not None:
            self.jsonld.append("".join(self._buf))
            self._buf = None
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()
        if tag == "title":
            self._in_title = False
        if tag == "h1" and self._h1 is not None:
            self.h1.append("".join(self._h1).strip())
            self._h1 = None
        elif tag == "a" and self._link is not None:
            self.links.append((self._link[0], "".join(self._link[1]).strip()))
            self._link = None

    def handle_data(self, data):
        if self._buf is not None:
            self._buf.append(data)
            return
        if self._stack:
            return
        if self._in_title:
            self.title += data
            return
        self.text.append(data)
        if self._h1 is not None:
            self._h1.append(data)
        if self._link is not None:
            self._link[1].append(data)


def _jsonld_objects(page):
    out = []
    for raw in page.jsonld:
        try:
            data = json.loads(raw)
        except ValueError:
            continue                                     # malformed structured data is ignored, never guessed
        out += data if isinstance(data, list) else [data]
    return [o for o in out if isinstance(o, dict)]


def load_site(site_dir):
    manifest = load_json(os.path.join(site_dir, "site.json"))
    if not manifest.get("base_url", "").startswith(("http://", "https://")):
        raise DiagnosisError("site.json needs base_url")
    return manifest


def _resolve(root, base_url, page_rel, href):
    """Classify a link: ('internal', rel_path) | ('contact', scheme) | ('external', url) | ('skip', None)."""
    if href.startswith("#") or not href.strip():
        return "skip", None
    url = urljoin(urljoin(base_url, page_rel), href)
    p = urlparse(url)
    if p.scheme in ("tel", "mailto"):
        return "contact", p.scheme
    if p.scheme not in ("http", "https") or p.netloc != urlparse(base_url).netloc:
        return "external", url
    rel = p.path.lstrip("/") or "index.html"
    if rel.endswith("/"):
        rel += "index.html"
    rel = os.path.normpath(rel)
    if rel.startswith("..") or os.path.isabs(rel):
        return "internal", None                          # escapes the site: unresolvable, never read
    return "internal", rel


def _read(root, rel, max_bytes):
    path = os.path.realpath(os.path.join(root, rel))
    if not path.startswith(os.path.realpath(root) + os.sep) or not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        data = f.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise DiagnosisError(f"page too large: {rel}")
    return data.decode("utf-8", errors="replace")


def crawl(site_dir, manifest, cfg):
    """Breadth-first over internal .html links, local files only, at most cfg['max_pages'] pages."""
    pages, queue, broken, truncated = {}, ["index.html"], set(), False
    while queue:
        rel = queue.pop(0)
        if rel in pages:
            continue
        if len(pages) >= cfg["max_pages"]:
            truncated = True
            break
        html = _read(site_dir, rel, cfg["max_page_bytes"])
        if html is None:
            broken.add(rel)
            continue
        page = Page()
        page.feed(html)
        pages[rel] = (html, page)
        for href, _ in page.links:
            kind, target = _resolve(site_dir, manifest["base_url"], rel, href)
            if kind == "internal":
                if target is None:
                    broken.add(href)
                elif target.endswith(".html"):
                    queue.append(target)
                elif _read(site_dir, target, cfg["max_page_bytes"]) is None:
                    broken.add(target)
    return pages, broken, truncated


def run_checks(site_dir, manifest, campaign, cfg=None):
    """Pure function over local files → {code: {status, measured, reason}}, facts, pages, crawl info."""
    cfg = cfg or rules()
    pages, broken, truncated = crawl(site_dir, manifest, cfg)
    if "index.html" not in pages:
        raise DiagnosisError("index.html missing")
    home_html, home = pages["index.html"]
    ld = _jsonld_objects(home)
    results = {}

    missing = [name for name, ok in (("title", (home.title or "").strip()),
                                     ("description", home.meta.get("description", "").strip()),
                                     ("h1", any(home.h1))) if not ok]
    if "noindex" in home.meta.get("robots", "").lower():
        missing.append("noindex")
    results["SEO_BASICS_MISSING"] = {"status": "DETECTED" if missing else "NOT_DETECTED",
                                     "measured": ";".join(missing) or None, "reason": "home page HTML"}

    types = {t for o in ld for t in ([o.get("@type")] if isinstance(o.get("@type"), str) else o.get("@type") or [])}
    visible = " ".join(home.text)
    area_in_text = [m for m in campaign["area"]["municipalities"] if m in visible]
    has_local = bool(types & set(cfg["local_business_types"])) or home.addresses > 0 or bool(area_in_text)
    results["NO_LOCAL_SIGNALS"] = {"status": "NOT_DETECTED" if has_local else "DETECTED", "measured": None,
                                   "reason": "JSON-LD LocalBusiness, <address> or campaign area in visible text"}

    n_broken = len(broken)
    if n_broken >= cfg["broken_internal_links_min"]:
        status = "DETECTED"
    else:
        status = "UNKNOWN" if truncated else "NOT_DETECTED"
    results["BROKEN_INTERNAL_LINKS"] = {"status": status, "measured": n_broken,
                                        "reason": f"{len(pages)} local pages crawled" + (" (truncated)" if truncated else "")}

    http_res = sorted({r for _, (_, p) in pages.items() for r in p.resources if r.startswith("http://")})
    if not manifest["base_url"].startswith("https://"):
        results["MIXED_CONTENT"] = {"status": "UNKNOWN", "measured": None, "reason": "page not served over HTTPS"}
    else:
        results["MIXED_CONTENT"] = {"status": "DETECTED" if http_res else "UNKNOWN", "measured": len(http_res) or None,
                                    "reason": "static HTML references only; runtime requests need a browser"}

    viewport = home.meta.get("viewport", "")
    results["NOT_MOBILE_READY"] = ({"status": "DETECTED", "measured": "no viewport meta", "reason": "home page HTML"}
                                   if not viewport else
                                   {"status": "UNKNOWN", "measured": None, "reason": "viewport present; layout needs a browser"})

    kinds = [_resolve(site_dir, manifest["base_url"], "index.html", h)[0] for h, _ in home.links]
    contact = ("contact" in kinds or home.forms > 0 or
               any("contact" in (h + " " + t).lower() for h, t in home.links))
    results["NO_MOBILE_CONTACT_PATH"] = (
        {"status": "UNKNOWN", "measured": None, "reason": "contact path exists; position on mobile needs a browser"}
        if contact else {"status": "DETECTED", "measured": "no tel:, mailto:, form or contact link", "reason": "home page HTML"})

    for code in cfg["not_run_needs_network_or_browser"]:
        results[code] = {"status": "UNKNOWN", "measured": None, "reason": "not run: needs network or browser"}

    facts = _facts(home_html, home, ld, types, area_in_text, cfg)
    return {"results": results, "facts": facts, "pages": {rel: html for rel, (html, _) in pages.items()},
            "broken_links": sorted(broken), "truncated": truncated}


def _facts(html, home, ld, types, area_in_text, cfg):
    """Basic site facts. KNOWN only with a literal snippet from the page source; text matches are INFERRED."""
    facts = []

    def known(field, value, snippet, personal="NONE"):
        if snippet and snippet in html:
            facts.append({"field": field, "value": value, "claim_status": "KNOWN", "snippet": snippet,
                          "personal_data": personal})

    for href, _ in home.links:
        if href.startswith("tel:") and not any(f["field"] == "business.phone" for f in facts):
            known("business.phone", href[4:], href, "BUSINESS_CONTACT")
        if href.startswith("mailto:") and not any(f["field"] == "business.email" for f in facts):
            known("business.email", href[7:], href, "BUSINESS_CONTACT")
        if "servicio" in href.lower() and not any(f["field"].startswith("activity.signal.") for f in facts):
            known("activity.signal.service_pages", True, href)
    for o in ld:
        locality = (o.get("address") or {}).get("addressLocality") if isinstance(o.get("address"), dict) else None
        if isinstance(locality, str):
            known("business.municipality", locality, locality)
    for t in sorted(types):
        if t in cfg["schema_type_to_category"]:
            known("business.category", cfg["schema_type_to_category"][t], f'"{t}"')
            break
    dates = sorted(d[:10] for d in home.times if len(d) >= 10 and d[4] == "-" and d[7] == "-")
    if dates:
        known("business.activity_dated", dates[-1], f'datetime="{dates[-1]}')
    if not any(f["field"] == "business.municipality" for f in facts) and area_in_text:
        facts.append({"field": "business.municipality", "value": area_in_text[0], "claim_status": "INFERRED",
                      "snippet": None, "personal_data": "NONE"})
    return facts


def diagnose(store, site_dir, actor="system"):
    """Run the static checks on one local site and record evidence, findings and events for its lead."""
    manifest = load_site(site_dir)
    lead = store.lead(manifest["lead"]["lead_id"])
    if lead is None:
        raise DiagnosisError("lead not imported")
    if lead["diagnosis_recorded"]:
        raise DiagnosisError("ALREADY_DIAGNOSED")
    cfg = rules()
    out = run_checks(site_dir, manifest, store.campaign(lead["campaign_id"]), cfg)
    url = manifest["base_url"]
    with store.tx():
        for html in out["pages"].values():
            store.conn.execute("INSERT OR IGNORE INTO captures(capture_sha256, text, available) VALUES (?,?,1)",
                               (sha256_text(html), html))
    home_sha = sha256_text(out["pages"]["index.html"])
    common = {"schema_version": "waos.evidence.v1", "subject": {"lead_id": lead["lead_id"], "entity_key": lead["entity_key"]},
              "retrieved_at": store.now(), "confidence": "HIGH", "proposed_by": "worker:diagnose@1.0.0",
              "data_mode": lead["data_mode"]}
    method = {"tool": "waos.diagnose", "tool_version": cfg["procedure_version"], "procedure_id": "STATIC-HTML"}
    recorded = []
    for fact in out["facts"]:
        ev = dict(common, evidence_id=new_id("ev_"), source_class="OFFICIAL", evidence_origin="FIRST_PARTY_WEB",
                  method=method, source_url=url, capture_sha256=home_sha if fact["claim_status"] == "KNOWN" else None,
                  seen_in="STRUCTURED_DATA" if fact["field"] in ("business.municipality", "business.category") else "PAGE",
                  **fact)
        if E.record(store, ev, actor):
            recorded.append(ev["evidence_id"])
    findings = []
    for code in CHECKS:
        r = out["results"][code]
        known = r["status"] != "UNKNOWN"
        ev = dict(common, evidence_id=new_id("ev_"), field=f"site.check.{code}",
                  value=r["status"] if known else None, claim_status="KNOWN" if known else "UNKNOWN",
                  source_class="MEASUREMENT", evidence_origin="MEASUREMENT",
                  method=dict(method, procedure_id="STATIC-HTML" if known else "NOT_RUN"),
                  source_url=url, snippet=None, personal_data="NONE")
        if not E.record(store, ev, actor):              # our own measurement record must never be invalid
            raise DiagnosisError(f"CHECK_EVIDENCE_REJECTED:{code}")
        if r["status"] == "NOT_DETECTED":
            continue
        doc = {"schema_version": "waos.finding.v1", "finding_id": new_id("fnd_"), "lead_id": lead["lead_id"],
               "code": code, "technical_severity": cfg["severity"][code],
               "claim_status": "KNOWN" if r["status"] == "DETECTED" else "UNKNOWN",
               "measured_value": r["measured"], "threshold_param": "P-05" if code == "BROKEN_INTERNAL_LINKS" else None,
               "rule_version": cfg["procedure_version"], "evidence_ids": [ev["evidence_id"]], "sales_safe": True,
               "detected_at": store.now(), "data_mode": lead["data_mode"]}
        schema.validate("finding", doc)
        findings.append(doc)
    lead["diagnosis_recorded"] = True
    with store.tx():
        for doc in findings:
            store.conn.execute("INSERT INTO findings(finding_id, lead_id, code, technical_severity, claim_status, doc)"
                               " VALUES (?,?,?,?,?,?)", (doc["finding_id"], lead["lead_id"], doc["code"],
                                                         doc["technical_severity"], doc["claim_status"],
                                                         json.dumps(doc, ensure_ascii=False)))
            store.event("finding.recorded", actor, lead["lead_id"],
                        {"finding_id": doc["finding_id"], "code": doc["code"], "claim_status": doc["claim_status"],
                         "technical_severity": doc["technical_severity"]}, refs=[doc["finding_id"]])
        store.put_lead(lead, last_transition_at=store.last_transition_at(lead["lead_id"]))
        counts = {s: sum(1 for r in out["results"].values() if r["status"] == s)
                  for s in ("DETECTED", "NOT_DETECTED", "UNKNOWN")}
        store.event("diagnosis.completed", actor, lead["lead_id"],
                    {"site_id": manifest["site_id"], "procedure_version": cfg["procedure_version"],
                     "pages_crawled": len(out["pages"]), "broken_links": len(out["broken_links"]), **counts,
                     "facts_recorded": len(recorded)})
    return out


# ── M2a demo: one command, fresh database, readable and traceable output

def corpus_fixture(corpus_dir):
    corpus = load_json(os.path.join(corpus_dir, "corpus.json"))
    leads = [{"lead": load_site(os.path.join(corpus_dir, sid))["lead"]} for sid in corpus["sites"]]
    return corpus, {"schema_version": "waos.fixture.v1", "data_mode": corpus["data_mode"],
                    "campaign": corpus["campaign"], "captures": {}, "leads": leads}


def _facts_of(store, lead_id):
    return {e["field"]: e["value"] for e in store.evidence_for(lead_id)
            if not e["field"].startswith("site.check.") and e["claim_status"] in ("KNOWN", "INFERRED")}


def _masked(facts):
    """Report files live outside the database (no retention/erasure): personal values appear only as a hash."""
    return {k: (f"[personal sha256:{sha256_text(str(v))[:12]}]" if k in E.PERSONAL_FIELDS else v)
            for k, v in facts.items()}


def run_demo(corpus_dir, out_dir, clock=None):
    from . import assessment, workflow
    from .export import export_csv
    from .ingest import import_fixture
    from .store import Store
    os.makedirs(out_dir, exist_ok=True)
    db = os.path.join(out_dir, "m2a.sqlite3")
    if os.path.exists(db):
        os.remove(db)
    store = Store(db, clock=clock)
    corpus, fixture = corpus_fixture(corpus_dir)
    import_fixture(store, fixture)
    sites, tally = [], {}
    for sid in corpus["sites"]:
        site_dir = os.path.join(corpus_dir, sid)
        manifest = load_site(site_dir)
        lead_id = manifest["lead"]["lead_id"]
        workflow.transition(store, lead_id, "IDENTITY_RESOLVED", "system")
        out = diagnose(store, site_dir)
        workflow.transition(store, lead_id, "DIAGNOSED", "system")
        score = assessment.score_lead(store, lead_id)
        workflow.transition(store, lead_id, "SCORED", "system")
        expected = manifest["expected"]
        actual = {c: out["results"][c]["status"] for c in CHECKS}
        mismatches = {c: {"expected": expected["checks"][c], "actual": actual[c]}
                      for c in CHECKS if expected["checks"][c] != actual[c]}
        for c in CHECKS:
            exp_d, act_d = expected["checks"][c] == "DETECTED", actual[c] == "DETECTED"
            t = tally.setdefault(c, {"TP": 0, "FP": 0, "FN": 0, "TN": 0, "UNKNOWN": 0})
            if actual[c] == "UNKNOWN":
                t["UNKNOWN"] += 1
            else:
                t["TP" if exp_d and act_d else "FP" if act_d else "FN" if exp_d else "TN"] += 1
        facts = _facts_of(store, lead_id)
        sites.append({"site_id": sid, "lead_id": lead_id, "purpose": manifest["purpose"], "checks": actual,
                      "measured": {c: out["results"][c]["measured"] for c in CHECKS if out["results"][c]["measured"]},
                      "check_mismatches": mismatches, "facts": _masked(facts), "facts_match": facts == expected["facts"],
                      "bucket": score["layer3"]["bucket"], "bucket_expected": expected["bucket"],
                      "TG": {k: score["layer1"]["TG"][k] for k in ("floor", "ceiling")},
                      "IM": {k: score["layer2"]["IM"][k] for k in ("floor", "ceiling")},
                      "pages_crawled": len(out["pages"]), "broken_links": out["broken_links"]})
    export = export_csv(store, os.path.join(out_dir, "leads_SYNTHETIC_m2a.csv"))
    report = {"corpus": corpus_dir, "database": db, "procedure_version": rules()["procedure_version"],
              "sites": sites, "detector_tally": tally, "export": export,
              "all_match": all(not s["check_mismatches"] and s["facts_match"] and s["bucket"] == s["bucket_expected"]
                               for s in sites)}
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    store.close()
    return report


def print_report(report):
    mark = lambda ok: "ok " if ok else "XX "
    print(f"M2a static diagnosis demo — procedure {report['procedure_version']} — local synthetic files only\n")
    print(f"{'site':<18} {'detected':<72} {'unknown':>7}  {'bucket (expected)':<34} labels")
    for s in report["sites"]:
        detected = ",".join(c for c, v in s["checks"].items() if v == "DETECTED") or "-"
        unknown = sum(1 for v in s["checks"].values() if v == "UNKNOWN")
        ok = not s["check_mismatches"] and s["facts_match"] and s["bucket"] == s["bucket_expected"]
        print(f"{s['site_id']:<18} {detected:<72} {unknown:>7}  {s['bucket']+' ('+str(s['bucket_expected'])+')':<34} {mark(ok)}")
        for c, m in s["check_mismatches"].items():
            print(f"{'':<18}   mismatch {c}: expected {m['expected']}, got {m['actual']}")
        if not s["facts_match"]:
            print(f"{'':<18}   facts differ: {s['facts']}")
    print("\nDetector tally over the corpus (UNKNOWN = not verifiable without network/browser, never counted as a pass):")
    for c, t in report["detector_tally"].items():
        print(f"  {c:<24} TP={t['TP']} FP={t['FP']} FN={t['FN']} TN={t['TN']} UNKNOWN={t['UNKNOWN']}")
    print(f"\nAll labels match: {report['all_match']}")
    print(f"Report: {os.path.join(os.path.dirname(report['database']), 'report.json')}")
    print(f"CSV:    {report['export']['path']}")
    print(f"Trace:  python3 -m waos --db {report['database']} trace {report['sites'][0]['lead_id']}")
