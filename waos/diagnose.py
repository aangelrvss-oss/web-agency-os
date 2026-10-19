"""M2a: static diagnosis of LOCAL synthetic websites (files on disk). No network, no browser.

Each catalogue check returns DETECTED, NOT_DETECTED or UNKNOWN. NOT_DETECTED is only returned when the check is fully
decidable from the HTML files; anything that needs HTTP, TLS or a browser is UNKNOWN, never a pass.
Results are stored as M1 evidence (site facts + one MEASUREMENT record per check) and findings (DETECTED → KNOWN,
UNKNOWN → UNKNOWN, which only raises score ceilings). Page content is treated as data: it is parsed, never executed.
"""
import json
import os
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from . import evidence as E
from . import schema
from .util import RULES, load_json, new_id, sha256_text

CHECKS = ("SEO_BASICS_MISSING", "NO_LOCAL_SIGNALS", "BROKEN_INTERNAL_LINKS", "MIXED_CONTENT", "NOT_MOBILE_READY",
          "NO_MOBILE_CONTACT_PATH", "NO_HTTPS", "TLS_INVALID", "SITE_DOWN", "SLOW_MOBILE", "LAYOUT_SHIFT", "A11Y_SERIOUS")
RESOURCE_TAGS = {"img", "script", "iframe", "source", "video", "audio", "embed"}
SKIP_TAGS = {"script", "style", "noscript", "template"}
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
WHATSAPP_NUMBER = re.compile(r"\d{6,15}")
# Why a check stayed UNKNOWN; stored as the check evidence's method.procedure_id so the audit can be rebuilt from the DB.
REASONS = ("NOT_RUN", "STATIC_INCONCLUSIVE", "NOT_HTTPS_CAPTURE", "CRAWL_TRUNCATED", "HOME_NOT_CAPTURED",
           "AMBIGUOUS_SIGNAL", "CONTACT_PATH_FOUND")


class DiagnosisError(Exception):
    pass


def rules():
    return load_json(os.path.join(RULES, "diagnosis.v1.json"))


class Page(HTMLParser):
    """Collects what the static checks need. Comments are ignored by HTMLParser, so links inside them never count.

    Like a browser, an open <a> is closed by the next <a> and an open <h1> by the next heading; both are closed at the
    end of the document (malformed or truncated HTML). `forms` counts forms a visitor could use to write to the
    business: site-search forms (role="search", an input type="search", or a search action) are not counted."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self.meta, self.h1, self.links, self.resources = None, {}, [], [], []
        self.robots = []
        self.jsonld, self.times, self.text, self.forms, self.addresses = [], [], [], 0, 0
        self._stack, self._buf, self._link, self._h1, self._in_title = [], None, None, None, False
        self._form = None

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
            if a["name"].lower() == "robots":
                self.robots.append(a.get("content", ""))
        elif tag in HEADINGS:
            self._close_h1()
            if tag == "h1":
                self._h1 = []
        elif tag == "a":
            self._close_link()
            if "href" in a:
                self._link = [a["href"], []]
        elif tag in RESOURCE_TAGS and a.get("src"):
            self.resources.append(a["src"])
        elif tag == "link" and a.get("href") and set(a.get("rel", "").lower().split()) & {"stylesheet", "icon"}:
            self.resources.append(a["href"])
        elif tag == "time" and a.get("datetime"):
            self.times.append(a["datetime"])
        elif tag == "form":
            self._close_form()
            action = a.get("action", "").lower()
            self._form = {"search": a.get("role", "").lower() == "search" or "search" in action or "buscar" in action}
        elif tag == "input" and self._form is not None and a.get("type", "").lower() == "search":
            self._form["search"] = True
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
        if tag == "h1":
            self._close_h1()
        elif tag == "a":
            self._close_link()
        elif tag == "form":
            self._close_form()

    def _close_form(self):
        if self._form is not None and not self._form["search"]:
            self.forms += 1
        self._form = None

    def _close_h1(self):
        if self._h1 is not None:
            self.h1.append("".join(self._h1).strip())
            self._h1 = None

    def _close_link(self):
        if self._link is not None:
            self.links.append((self._link[0], "".join(self._link[1]).strip()))
            self._link = None

    def close(self):
        super().close()
        self._close_h1()
        self._close_link()
        self._close_form()

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
    flat = []
    for o in out:
        if isinstance(o, dict):
            flat.append(o)
            graph = o.get("@graph")
            flat += [g for g in graph if isinstance(g, dict)] if isinstance(graph, list) else []
    return flat


def load_site(site_dir):
    manifest = load_json(os.path.join(site_dir, "site.json"))
    if not manifest.get("base_url", "").startswith(("http://", "https://")):
        raise DiagnosisError("site.json needs base_url")
    return manifest


def _whatsapp(href):
    """A WhatsApp click-to-chat link with a number: https://wa.me/<n>, https://api.whatsapp.com/send?phone=<n> or
    whatsapp://send?phone=<n>. It is a possible contact path only: nothing says the number works or is answered."""
    p = urlparse(href.strip())
    host = (p.hostname or "").lower()
    if p.scheme == "https" and host == "wa.me":
        return bool(WHATSAPP_NUMBER.fullmatch(p.path.strip("/")))
    phone = parse_qs(p.query).get("phone", [""])[0]
    return bool(WHATSAPP_NUMBER.fullmatch(phone)) and (
        (p.scheme == "https" and host == "api.whatsapp.com" and p.path.rstrip("/") == "/send")
        or (p.scheme == "whatsapp" and host == "send"))


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
    rel = unquote(p.path).lstrip("/") or "index.html"      # servers decode %20 etc.; decoded before the checks below
    if "\x00" in rel:
        return "internal", None
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
        page.close()
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
    if "index.html" not in pages:                        # absence of evidence: nothing about the site can be said
        results = {c: _unknown("HOME_NOT_CAPTURED", "home page not in the capture") for c in CHECKS}
        return {"results": results, "facts": [], "pages": {rel: html for rel, (html, _) in pages.items()},
                "broken_links": [], "truncated": truncated}
    home_html, home = pages["index.html"]
    ld = _jsonld_objects(home)
    results = {}

    missing = [name for name, ok in (("title", (home.title or "").strip()),
                                     ("description", home.meta.get("description", "").strip()),
                                     ("h1", any(home.h1))) if not ok]
    if any("noindex" in r.lower() for r in home.robots):     # contradictory robots tags: the most restrictive wins
        missing.append("noindex")
    results["SEO_BASICS_MISSING"] = {"status": "DETECTED" if missing else "NOT_DETECTED",
                                     "measured": ";".join(missing) or None, "reason": "home page HTML"}

    types = {t for o in ld for t in ([o.get("@type")] if isinstance(o.get("@type"), str) else o.get("@type") or [])}
    visible = " ".join(home.text)
    area_in_text = [m for m in campaign["area"]["municipalities"]
                    if re.search(r"(?<!\w)" + re.escape(m) + r"(?!\w)", visible)]       # whole name, not a substring
    partial = [m for m in campaign["area"]["municipalities"] if m in visible and m not in area_in_text]
    has_local = bool(types & set(cfg["local_business_types"])) or home.addresses > 0 or bool(area_in_text)
    reason = "JSON-LD LocalBusiness, <address> or campaign area in visible text"
    if has_local or not partial:
        results["NO_LOCAL_SIGNALS"] = {"status": "NOT_DETECTED" if has_local else "DETECTED", "measured": None,
                                       "reason": reason}
    else:                                                # e.g. "Norteña" around "Norte": a place we cannot recognise
        results["NO_LOCAL_SIGNALS"] = _unknown("AMBIGUOUS_SIGNAL", "text contains a campaign area name only "
                                                                   "inside a longer word")

    n_broken = len(broken)
    if n_broken >= cfg["broken_internal_links_min"]:
        status = "DETECTED"
    else:
        status = "UNKNOWN" if truncated else "NOT_DETECTED"
    results["BROKEN_INTERNAL_LINKS"] = {"status": status, "measured": n_broken,
                                        "reason": f"{len(pages)} local pages crawled" + (" (truncated)" if truncated else "")}
    if status == "UNKNOWN":
        results["BROKEN_INTERNAL_LINKS"]["reason_code"] = "CRAWL_TRUNCATED"

    http_res = sorted({r for _, (_, p) in pages.items() for r in p.resources if r.startswith("http://")})
    if not manifest["base_url"].startswith("https://"):
        results["MIXED_CONTENT"] = _unknown("NOT_HTTPS_CAPTURE", "page not served over HTTPS")
    elif http_res:
        results["MIXED_CONTENT"] = {"status": "DETECTED", "measured": len(http_res), "reason": "static HTML references"}
    else:
        results["MIXED_CONTENT"] = _unknown("STATIC_INCONCLUSIVE", "no http:// reference in static HTML; "
                                                                    "runtime requests need a browser")

    viewport = home.meta.get("viewport", "")
    results["NOT_MOBILE_READY"] = ({"status": "DETECTED", "measured": "no viewport meta", "reason": "home page HTML"}
                                   if not viewport else
                                   _unknown("STATIC_INCONCLUSIVE", "viewport present; layout needs a browser"))

    resolved = [_resolve(site_dir, manifest["base_url"], "index.html", h) for h, _ in home.links]
    linked = {target for kind, target in resolved if kind == "internal" and target in pages}
    contact = (any(kind == "contact" for kind, _ in resolved) or home.forms > 0
               or any(_whatsapp(h) for h, _ in home.links)
               or any(pages[t][1].forms > 0 for t in linked)                  # e.g. "Pide presupuesto" → form page
               or any("contact" in (h + " " + t).lower() for h, t in home.links))
    results["NO_MOBILE_CONTACT_PATH"] = (
        _unknown("CONTACT_PATH_FOUND", "possible contact path; not tested, mobile position needs a browser")
        if contact else {"status": "DETECTED", "measured": "no tel:, mailto:, WhatsApp, contact form or contact link",
                         "reason": "home page and the pages it links to"})

    for code in cfg["not_run_needs_network_or_browser"]:
        results[code] = _unknown("NOT_RUN", "not run: needs network or browser")

    facts = _facts(home_html, home, ld, types, area_in_text, cfg)
    return {"results": results, "facts": facts, "pages": {rel: html for rel, (html, _) in pages.items()},
            "broken_links": sorted(broken), "truncated": truncated}


def _unknown(reason_code, reason):
    return {"status": "UNKNOWN", "measured": None, "reason": reason, "reason_code": reason_code}


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
    home_sha = sha256_text(out["pages"]["index.html"]) if "index.html" in out["pages"] else None
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
                  method=dict(method, procedure_id="STATIC-HTML" if known else r["reason_code"]),
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
    """Site facts as {field: value}; a field with several different KNOWN values is a sorted list (contradiction)."""
    rows = [e for e in store.evidence_for(lead_id)
            if not e["field"].startswith("site.check.") and e["claim_status"] in ("KNOWN", "INFERRED")]
    facts = {}
    for field in sorted({e["field"] for e in rows}):
        status, value, _ = E.resolve(rows, field)
        facts[field] = (sorted({e["value"] for e in rows if e["field"] == field and e["claim_status"] == "KNOWN"})
                        if status == "CONFLICTING" else value)
    return facts


def _masked(facts):
    """Report files live outside the database (no retention/erasure): personal values appear only as a hash."""
    return {k: (f"[personal sha256:{sha256_text(str(v))[:12]}]" if k in E.PERSONAL_FIELDS else v)
            for k, v in facts.items()}


def _safe_path(path):
    """Broken-link paths come from untrusted HTML: keep plain path characters only and mask long digit runs."""
    return re.sub(r"\d{6,}", "######", re.sub(r"[^A-Za-z0-9._/%-]", "?", path))[:80]


def _compare(manifest, actual):
    """Expected vs actual. A difference recorded in known_deviation is 'known'; any other difference, or a known
    deviation that no longer happens, is 'unexpected'."""
    expected, known = manifest["expected"], manifest.get("known_deviation", {}).get("actual", {})
    diffs = []
    for c in CHECKS:
        if expected["checks"][c] != actual["checks"][c]:
            diffs.append({"what": f"checks.{c}", "expected": expected["checks"][c], "actual": actual["checks"][c],
                          "known": known.get("checks", {}).get(c) == actual["checks"][c]})
    for key in ("facts", "bucket", "evaluation_status"):
        if expected[key] != actual[key]:
            diffs.append({"what": key, "expected": expected[key], "actual": actual[key],
                          "known": key in known and known[key] == actual[key]})
    stale = [f"checks.{c}" for c, v in known.get("checks", {}).items() if actual["checks"][c] != v]
    stale += [k for k in ("facts", "bucket", "evaluation_status") if k in known and actual[k] != known[k]]
    diffs += [{"what": w, "expected": "documented known deviation", "actual": "no longer happens", "known": False}
              for w in stale]
    return diffs


def run_demo(corpus_dir, out_dir, clock=None):
    """One command: fresh database, diagnosis + scoring + evaluation of every corpus site, then report.json,
    audit_report.md and the CSV. Without a clock the corpus `as_of` time is used, so every output is reproducible."""
    from . import assessment, audit, evaluation, workflow
    from .export import export_csv
    from .ingest import import_fixture
    from .store import Store
    from .util import parse_iso
    os.makedirs(out_dir, exist_ok=True)
    db = os.path.join(out_dir, "m2a.sqlite3")
    if os.path.exists(db):
        os.remove(db)
    corpus, fixture = corpus_fixture(corpus_dir)
    if clock is None:
        as_of = parse_iso(corpus["as_of"])
        clock = lambda: as_of                                         # noqa: E731
    store = Store(db, clock=clock)
    import_fixture(store, fixture)
    sites, tally, matrix = [], {}, {}
    for sid in corpus["sites"]:
        site_dir = os.path.join(corpus_dir, sid)
        manifest = load_site(site_dir)
        lead_id = manifest["lead"]["lead_id"]
        workflow.transition(store, lead_id, "IDENTITY_RESOLVED", "system")
        out = diagnose(store, site_dir)
        workflow.transition(store, lead_id, "DIAGNOSED", "system")
        score = assessment.score_lead(store, lead_id)
        workflow.transition(store, lead_id, "SCORED", "system")
        ev = evaluation.evaluate_lead(store, lead_id)
        expected = manifest["expected"]
        checks = {c: out["results"][c]["status"] for c in CHECKS}
        facts = _facts_of(store, lead_id)
        diffs = _compare(manifest, {"checks": checks, "facts": facts, "bucket": score["layer3"]["bucket"],
                                    "evaluation_status": ev["status"]})
        for c in CHECKS:
            exp_d, act_d = expected["checks"][c] == "DETECTED", checks[c] == "DETECTED"
            t = tally.setdefault(c, {"TP": 0, "FP": 0, "FN": 0, "TN": 0, "UNKNOWN": 0})
            if checks[c] == "UNKNOWN":
                t["UNKNOWN"] += 1
            else:
                t["TP" if exp_d and act_d else "FP" if act_d else "FN" if exp_d else "TN"] += 1
        row = matrix.setdefault(expected["evaluation_status"], {})
        row[ev["status"]] = row.get(ev["status"], 0) + 1
        sites.append({"site_id": sid, "lead_id": lead_id, "purpose": manifest["purpose"],
                      "evaluation_status": ev["status"], "evaluation_expected": expected["evaluation_status"],
                      "bucket": score["layer3"]["bucket"], "bucket_expected": expected["bucket"],
                      "confirmed": ev["confirmed"], "pending": ev["pending"], "checks": checks,
                      "measured": {c: out["results"][c]["measured"] for c in CHECKS if out["results"][c]["measured"]},
                      "facts": _masked(facts),
                      "TG": {k: score["layer1"]["TG"][k] for k in ("floor", "ceiling")},
                      "IM": {k: score["layer2"]["IM"][k] for k in ("floor", "ceiling")},
                      "pages_crawled": len(out["pages"]), "broken_links": [_safe_path(b) for b in out["broken_links"]],
                      "deviations": diffs,
                      "known_deviation_reason": manifest.get("known_deviation", {}).get("reason")})
    export = export_csv(store, os.path.join(out_dir, "leads_SYNTHETIC_m2a.csv"))
    audit_path = os.path.join(out_dir, "audit_report.md")
    with open(audit_path, "w", encoding="utf-8") as f:
        f.write(audit.render(store, [s["lead_id"] for s in sites], "Auditoría de diagnóstico — corpus sintético M2a"))
    unexpected = sum(1 for s in sites for d in s["deviations"] if not d["known"])
    report = {"corpus": corpus_dir, "database": db, "as_of": store.now(), "procedure_version": rules()["procedure_version"],
              "evaluation_scope": rules()["evaluation_scope"], "sites": sites, "detector_tally": tally,
              "evaluation_matrix": matrix, "export": export, "audit_report": audit_path,
              "known_deviations": sum(1 for s in sites for d in s["deviations"] if d["known"]),
              "unexpected_deviations": unexpected,
              "all_match": not any(s["deviations"] for s in sites)}
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    store.close()
    return report


def print_report(report):
    print(f"M2a.1 diagnosis demo — procedure {report['procedure_version']} — local synthetic files only — "
          f"clock {report['as_of']}\n")
    print(f"{'site':<22} {'evaluation (expected)':<46} {'review bucket (expected)':<34} {'confirmed':<9} "
          f"{'unverified':<10} result")
    for s in report["sites"]:
        ev = f"{s['evaluation_status']} ({s['evaluation_expected']})"
        bucket = f"{s['bucket']} ({s['bucket_expected']})"
        in_scope = sum(1 for p in s["pending"] if p["in_scope"])
        unexpected = [d for d in s["deviations"] if not d["known"]]
        mark = "ok" if not s["deviations"] else "KNOWN DEVIATION" if not unexpected else "UNEXPECTED"
        print(f"{s['site_id']:<22} {ev:<46} {bucket:<34} {len(s['confirmed']):<9} "
              f"{str(in_scope) + '/' + str(len(s['pending'])):<10} {mark}")
        for d in s["deviations"]:
            print(f"{'':<22}   {'known' if d['known'] else 'UNEXPECTED'} {d['what']}: expected {d['expected']}, "
                  f"got {d['actual']}")
    print("\nEvaluation status, expected → actual:")
    for exp, row in sorted(report["evaluation_matrix"].items()):
        print(f"  {exp:<22} → " + ", ".join(f"{k}: {v}" for k, v in sorted(row.items())))
    print("\nDetector tally against the labels (UNKNOWN = not verifiable here, never counted as a pass):")
    for c, t in report["detector_tally"].items():
        print(f"  {c:<24} TP={t['TP']} FP={t['FP']} FN={t['FN']} TN={t['TN']} UNKNOWN={t['UNKNOWN']}")
    print(f"\nEvaluation scope: {', '.join(report['evaluation_scope'])} (the other checks are listed as unverified)")
    print(f"Deviations from labels: {report['unexpected_deviations']} unexpected, {report['known_deviations']} known "
          "(documented in site.json known_deviation)")
    print(f"Audit:  {report['audit_report']}")
    print(f"Report: {os.path.join(os.path.dirname(report['database']), 'report.json')}")
    print(f"CSV:    {report['export']['path']}")
    print(f"Trace:  python3 -m waos --db {report['database']} trace {report['sites'][0]['lead_id']}")
