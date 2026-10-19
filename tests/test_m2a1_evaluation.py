"""M2a.1: evaluation status, UNKNOWN invariants, edge cases, export and the readable audit. Local files only."""
import csv
import os
import re
import shutil
import tempfile

from waos import audit, diagnose, evaluation, export, workflow
from waos.ingest import import_fixture

from .support import Base, Clock
from .test_m2a_diagnosis import CORPUS, SITES, Corpus, site_dir

SCOPE = ("SEO_BASICS_MISSING", "NO_LOCAL_SIGNALS", "BROKEN_INTERNAL_LINKS")
M1_COLUMNS = export.COLUMNS[:export.COLUMNS.index("exported_at") + 1]


def check_ev(code, value, n=0, status=None, erased=False, procedure="STATIC-HTML"):
    return {"evidence_id": f"ev_{code.lower()}_{n}", "field": f"site.check.{code}", "value": value,
            "claim_status": status or ("UNKNOWN" if value is None else "KNOWN"), "erased": erased,
            "source_class": "MEASUREMENT", "method": {"tool_version": "static-html-1.0.0", "procedure_id": procedure}}


def finding(code, claim_status, evidence_ids):
    return {"finding_id": f"fnd_{code.lower()}", "code": code, "claim_status": claim_status,
            "evidence_ids": evidence_ids}


def all_clear():
    return [check_ev(c, "NOT_DETECTED") if c in SCOPE else check_ev(c, None, procedure="NOT_RUN")
            for c in diagnose.CHECKS]


class ThreeStates(Base):
    """evaluate() is a pure function over evidence and findings."""

    def test_no_problems_found_needs_every_in_scope_check_and_lists_the_rest(self):
        ev = evaluation.evaluate(all_clear(), [])
        self.assertEqual(ev["status"], "NO_PROBLEMS_FOUND")
        self.assertEqual(ev["clear"], list(SCOPE))
        self.assertEqual(len(ev["pending"]), len(diagnose.CHECKS) - len(SCOPE))     # never a full guarantee
        self.assertTrue(all(not p["in_scope"] for p in ev["pending"]))

    def test_one_unknown_in_scope_check_means_insufficient_evidence(self):
        for code in SCOPE:
            evidence = [e for e in all_clear() if e["field"] != f"site.check.{code}"]
            for variant in ([check_ev(code, None, procedure="CRAWL_TRUNCATED")], []):
                ev = evaluation.evaluate(evidence + variant, [])
                self.assertEqual(ev["status"], "INSUFFICIENT_EVIDENCE", code)
                self.assertNotIn(code, ev["clear"])
                pending = {p["code"]: p for p in ev["pending"]}
                self.assertTrue(pending[code]["in_scope"])
                self.assertEqual(pending[code]["reason_code"], "CRAWL_TRUNCATED" if variant else "NO_EVIDENCE")

    def test_no_evidence_at_all_is_insufficient(self):
        ev = evaluation.evaluate([], [])
        self.assertEqual((ev["status"], ev["confirmed"], ev["clear"]), ("INSUFFICIENT_EVIDENCE", [], []))
        self.assertEqual(len(ev["pending"]), len(diagnose.CHECKS))

    def test_problems_found_needs_a_known_finding_with_valid_evidence(self):
        evidence = [e for e in all_clear() if "MIXED_CONTENT" not in e["field"]] + [check_ev("MIXED_CONTENT", "DETECTED")]
        ok = finding("MIXED_CONTENT", "KNOWN", ["ev_mixed_content_0"])
        self.assertEqual(evaluation.evaluate(evidence, [ok])["status"], "PROBLEMS_FOUND")
        partial = [e for e in evidence if "BROKEN" not in e["field"]]                # scope incomplete: still a problem
        self.assertEqual(evaluation.evaluate(partial, [ok])["confirmed"], ["MIXED_CONTENT"])

    def test_invalid_or_unknown_findings_are_never_confirmed(self):
        cases = {
            "unknown finding": ([check_ev("MIXED_CONTENT", None)], finding("MIXED_CONTENT", "UNKNOWN", ["ev_mixed_content_0"])),
            "evidence missing": ([], finding("MIXED_CONTENT", "KNOWN", ["ev_mixed_content_0"])),
            "evidence unknown": ([check_ev("MIXED_CONTENT", None)], finding("MIXED_CONTENT", "KNOWN", ["ev_mixed_content_0"])),
            "evidence erased": ([check_ev("MIXED_CONTENT", "DETECTED", erased=True)],
                                finding("MIXED_CONTENT", "KNOWN", ["ev_mixed_content_0"])),
            "no evidence ids": ([check_ev("MIXED_CONTENT", "DETECTED")], finding("MIXED_CONTENT", "KNOWN", [])),
        }
        for name, (extra, f) in cases.items():
            ev = evaluation.evaluate([e for e in all_clear() if "MIXED" not in e["field"]] + extra, [f])
            self.assertEqual(ev["confirmed"], [], name)
            self.assertNotEqual(ev["status"], "PROBLEMS_FOUND", name)
            self.assertIn("MIXED_CONTENT", [p["code"] for p in ev["pending"]], name)

    def test_contradictory_check_evidence_is_pending_not_clear(self):
        evidence = all_clear() + [check_ev("SEO_BASICS_MISSING", "DETECTED", n=1)]
        ev = evaluation.evaluate(evidence, [])
        self.assertEqual(ev["status"], "INSUFFICIENT_EVIDENCE")
        self.assertIn({"code": "SEO_BASICS_MISSING", "in_scope": True, "reason_code": "CONFLICTING_EVIDENCE"},
                      ev["pending"])

    def test_scope_is_a_rule_parameter(self):
        cfg = dict(diagnose.rules(), evaluation_scope=list(diagnose.CHECKS))           # e.g. after a browser phase
        self.assertEqual(evaluation.evaluate(all_clear(), [], cfg)["status"], "INSUFFICIENT_EVIDENCE")


class UnknownInvariants(Corpus):
    """Over the whole corpus: UNKNOWN never becomes a confirmed problem nor a guarantee of absence."""

    def setUp(self):
        super().setUp()
        self.outs = {}
        for sid in SITES:
            self.outs[sid] = diagnose.run_checks(site_dir(sid), diagnose.load_site(site_dir(sid)), self.corpus["campaign"])
            self.diagnose(sid)

    def test_unknown_checks_are_pending_never_confirmed_never_clear(self):
        for sid, out in self.outs.items():
            lead_id = f"lead_m2a_{sid}"
            ev = evaluation.evaluate_lead(self.store, lead_id)
            known_codes = {f["code"] for f in self.store.findings_for(lead_id) if f["claim_status"] == "KNOWN"}
            pending = {p["code"]: p for p in ev["pending"]}
            for code, r in out["results"].items():
                if r["status"] != "UNKNOWN":
                    continue
                self.assertNotIn(code, ev["confirmed"], f"{sid}/{code}")
                self.assertNotIn(code, known_codes, f"{sid}/{code}")
                self.assertNotIn(code, ev["clear"], f"{sid}/{code}")
                self.assertEqual(pending[code]["reason_code"], r["reason_code"], f"{sid}/{code}")
                if code in SCOPE:
                    self.assertNotEqual(ev["status"], "NO_PROBLEMS_FOUND", f"{sid}/{code}")

    def test_status_follows_the_definition_and_the_labels(self):
        for sid, out in self.outs.items():
            manifest = diagnose.load_site(site_dir(sid))
            ev = evaluation.evaluate_lead(self.store, manifest["lead"]["lead_id"])
            detected = sorted(c for c, r in out["results"].items() if r["status"] == "DETECTED")
            self.assertEqual(ev["confirmed"], detected, sid)
            if detected:
                expected = "PROBLEMS_FOUND"
            elif all(out["results"][c]["status"] == "NOT_DETECTED" for c in SCOPE):
                expected = "NO_PROBLEMS_FOUND"
            else:
                expected = "INSUFFICIENT_EVIDENCE"
            self.assertEqual(ev["status"], expected, sid)
            label = manifest.get("known_deviation", {}).get("actual", {}).get(
                "evaluation_status", manifest["expected"]["evaluation_status"])
            self.assertEqual(ev["status"], label, sid)

    def test_all_three_states_occur_in_the_corpus(self):
        states = {evaluation.evaluate_lead(self.store, f"lead_m2a_{sid}")["status"] for sid in SITES}
        self.assertEqual(states, set(evaluation.STATUSES))


class EdgeCases(Corpus):
    def results(self, sid):
        out = diagnose.run_checks(site_dir(sid), diagnose.load_site(site_dir(sid)), self.corpus["campaign"])
        return out, {c: r["status"] for c, r in out["results"].items()}

    def test_malformed_html_is_repaired_like_a_browser(self):
        page = diagnose.Page()
        page.feed('<h1>Uno<h2>Dos</h2><a href="tel:+34000000001">a <a href="b.html">b')
        page.close()
        self.assertEqual(page.h1, ["Uno"])
        self.assertEqual([h for h, _ in page.links], ["tel:+34000000001", "b.html"])
        out, st = self.results("s10_malformed")
        self.assertEqual((st["SEO_BASICS_MISSING"], st["NO_MOBILE_CONTACT_PATH"]), ("NOT_DETECTED", "UNKNOWN"))
        self.assertIn("business.phone", {f["field"] for f in out["facts"]})

    def test_encoded_relative_and_external_links_are_not_broken(self):
        out, st = self.results("s11_links")
        self.assertEqual((st["BROKEN_INTERNAL_LINKS"], out["broken_links"]), ("NOT_DETECTED", []))
        self.assertIn("galería.html", out["pages"])

    def test_decoding_cannot_escape_the_site(self):
        base = "https://local.example/"
        for href in ("%2e%2e/%2e%2e/secret.html", "a/%2e%2e%2f%2e%2e%2f..%2fsecret.html", "x%00.html"):
            kind, rel = diagnose._resolve("/nowhere", base, "index.html", href)
            self.assertEqual(kind, "internal", href)
            self.assertTrue(rel is None or not rel.startswith(".."), href)
        self.assertEqual(diagnose._resolve("/nowhere", base, "index.html", "x%00.html"), ("internal", None))
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "site"))
            with open(os.path.join(tmp, "secret.html"), "w") as f:
                f.write("<html><a href='tel:+34000000666'>x</a></html>")
            with open(os.path.join(tmp, "site", "index.html"), "w") as f:
                f.write('<a href="..%2fsecret.html">a</a> <a href="%2e%2e/secret.html">b</a> <a href="x%00.html">c</a>')
            pages, _, _ = diagnose.crawl(os.path.join(tmp, "site"), {"base_url": base}, diagnose.rules())
            self.assertEqual(list(pages), ["index.html"])
        finally:
            shutil.rmtree(tmp)

    def test_graph_jsonld_counts_as_local_signal(self):
        out, st = self.results("s08_good_variants")
        self.assertEqual(st["NO_LOCAL_SIGNALS"], "NOT_DETECTED")
        self.assertEqual({f["field"]: f["claim_status"] for f in out["facts"]}["business.municipality"], "KNOWN")

    def test_ambiguous_place_name_is_unknown_and_not_inferred(self):
        out, st = self.results("s12_ambiguous_local")
        self.assertEqual(out["results"]["NO_LOCAL_SIGNALS"]["reason_code"], "AMBIGUOUS_SIGNAL")
        self.assertNotIn("business.municipality", {f["field"] for f in out["facts"]})

    def test_contradictions_robots_and_municipality(self):
        out, st = self.results("s13_contradictory")
        self.assertEqual((st["SEO_BASICS_MISSING"], out["results"]["SEO_BASICS_MISSING"]["measured"]),
                         ("DETECTED", "noindex"))
        self.diagnose("s13_contradictory")
        workflow.transition(self.store, "lead_m2a_s13_contradictory", "DIAGNOSED", "system")
        from waos import assessment
        score = assessment.score_lead(self.store, "lead_m2a_s13_contradictory")
        self.assertEqual({g["gate_id"]: g["result"] for g in score["gates"]}["G_GEO"], "UNKNOWN")

    def test_missing_home_page_records_only_unknown(self):
        self.diagnose("s14_no_home")
        lead_id = "lead_m2a_s14_no_home"
        evidence = self.store.evidence_for(lead_id)
        self.assertEqual(len(evidence), len(diagnose.CHECKS))
        self.assertTrue(all(e["claim_status"] == "UNKNOWN" and e["method"]["procedure_id"] == "HOME_NOT_CAPTURED"
                            for e in evidence))
        self.assertTrue(all(f["claim_status"] == "UNKNOWN" for f in self.store.findings_for(lead_id)))
        self.assertEqual(self.events_of("evidence.rejected"), [])

    def test_crawl_limit_hides_broken_links_and_stays_unknown(self):
        out, st = self.results("s15_crawl_limit")
        self.assertTrue(out["truncated"])
        self.assertEqual((st["BROKEN_INTERNAL_LINKS"], out["broken_links"]), ("UNKNOWN", []))
        cfg = dict(diagnose.rules(), max_pages=100)            # with every page read the problem is there
        out = diagnose.run_checks(site_dir("s15_crawl_limit"), diagnose.load_site(site_dir("s15_crawl_limit")),
                                  self.corpus["campaign"], cfg)
        self.assertEqual(out["results"]["BROKEN_INTERNAL_LINKS"]["status"], "DETECTED")



def contact_result(home, extra=None):
    """NO_MOBILE_CONTACT_PATH for a throw-away local site whose home page body is `home`."""
    tmp = tempfile.mkdtemp()
    try:
        files = dict({"index.html": f"<html><head><title>t</title></head><body><h1>t</h1>{home}</body></html>"},
                     **(extra or {}))
        for rel, html in files.items():
            with open(os.path.join(tmp, rel), "w", encoding="utf-8") as f:
                f.write(html)
        campaign = {"area": {"municipalities": ["Villa Sintética Norte"]}}
        return diagnose.run_checks(tmp, {"base_url": "https://t.example/"}, campaign)["results"]["NO_MOBILE_CONTACT_PATH"]
    finally:
        shutil.rmtree(tmp)


class ContactChannels(Base):
    """A detectable channel is only a POSSIBLE contact path (UNKNOWN), never proof that it works or is answered."""

    def test_valid_whatsapp_links_are_a_possible_contact_path(self):
        for href in ("https://wa.me/34000000216", "https://wa.me/34000000216/", "https://api.whatsapp.com/send?phone=34000000216",
                     "https://api.whatsapp.com/send/?phone=34000000216&text=hola", "whatsapp://send?phone=34000000216",
                     " https://WA.ME/34000000216"):
            self.assertTrue(diagnose._whatsapp(href), href)
            r = contact_result(f'<a href="{href}">WhatsApp</a>')
            self.assertEqual((r["status"], r["reason_code"], r["measured"]), ("UNKNOWN", "CONTACT_PATH_FOUND", None), href)

    def test_invalid_whatsapp_lookalikes_are_not_channels(self):
        for href in ("https://wa.me/", "https://wa.me/hola", "https://wa.me/+34000000216", "https://wa.me/123",
                     "http://wa.me/34000000216", "https://wa.me.example.net/34000000216",
                     "https://evil.example/?u=https://wa.me/34000000216", "https://api.whatsapp.com/send",
                     "https://api.whatsapp.com/otro?phone=34000000216", "whatsapp://send", "javascript:wa.me/34000000216"):
            self.assertFalse(diagnose._whatsapp(href), href)
            self.assertEqual(contact_result(f'<a href="{href}">WhatsApp</a>')["status"], "DETECTED", href)

    def test_contact_forms_count_on_the_home_page_or_a_page_it_links_to(self):
        self.assertEqual(contact_result('<form action="enviar"><textarea></textarea></form>')["status"], "UNKNOWN")
        self.assertEqual(contact_result('<form><textarea>sin cerrar')["status"], "UNKNOWN")       # unclosed form
        quote = {"presupuesto.html": '<form action="#"><textarea></textarea></form>'}
        self.assertEqual(contact_result('<a href="presupuesto.html">Pide presupuesto</a>', quote)["status"], "UNKNOWN")
        two_hops = {"blog.html": '<a href="oculto.html">más</a>', "oculto.html": '<form action="#"><textarea></textarea></form>'}
        self.assertEqual(contact_result('<a href="blog.html">Blog</a>', two_hops)["status"], "DETECTED")  # crawled, 2 hops

    def test_search_forms_are_not_contact_channels(self):
        for form in ('<form role="search"><input name="q"></form>', '<form action="/buscar"><input name="q"></form>',
                     '<form action="/search"><input name="q"></form>', '<form><input type="search" name="q"></form>',
                     '<form role="SEARCH"><input type="SEARCH"></form>'):
            self.assertEqual(contact_result(form)["status"], "DETECTED", form)
        search_page = {"buscar.html": '<form role="search"><input type="search"></form>'}
        self.assertEqual(contact_result('<a href="buscar.html">Buscar</a>', search_page)["status"], "DETECTED")

    def test_real_absence_of_detectable_channels_is_detected(self):
        r = contact_result('<p>Hacemos reformas.</p><a href="https://www.example.org/">Asociación</a>')
        self.assertEqual((r["status"], r["measured"]),
                         ("DETECTED", "no tel:, mailto:, WhatsApp, contact form or contact link"))
        for home in ('<a href="tel:+34000000001">t</a>', '<a href="mailto:a@b.example">m</a>',
                     '<a href="contacto.html">Contacto</a>'):
            self.assertEqual(contact_result(home)["status"], "UNKNOWN", home)

    def test_corpus_whatsapp_and_no_channel_sites(self):
        campaign = load_campaign()
        s16 = diagnose.run_checks(site_dir("s16_whatsapp_contact"), diagnose.load_site(site_dir("s16_whatsapp_contact")),
                                  campaign)
        self.assertEqual(s16["results"]["NO_MOBILE_CONTACT_PATH"]["status"], "UNKNOWN")
        self.assertNotIn("business.phone", {f["field"] for f in s16["facts"]})     # a WhatsApp number is not a fact
        s17 = diagnose.run_checks(site_dir("s17_no_contact_channel"),
                                  diagnose.load_site(site_dir("s17_no_contact_channel")), campaign)
        self.assertEqual(s17["results"]["NO_MOBILE_CONTACT_PATH"]["status"], "DETECTED")


def load_campaign():
    return diagnose.corpus_fixture(CORPUS)[0]["campaign"]


class ExportAndAudit(Base):
    def setUp(self):
        super().setUp()
        self.out = os.path.join(self.tmp, "demo")
        self.report = diagnose.run_demo(CORPUS, self.out, clock=Clock())
        with open(self.report["export"]["path"], encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            self.header = next(reader)
            self.rows = {r[0]: dict(zip(self.header, r)) for r in reader}
        with open(self.report["audit_report"], encoding="utf-8") as f:
            self.audit = f.read()

    def test_csv_columns_are_additive_and_carry_status_apart_from_priority(self):
        self.assertEqual(self.header[:len(M1_COLUMNS)], list(M1_COLUMNS))               # M1 positions unchanged
        self.assertEqual(self.header[len(M1_COLUMNS):], ["evaluation_status", "evaluation_procedure", "checks_unverified"])
        for s in self.report["sites"]:
            row = self.rows[s["lead_id"]]
            self.assertEqual(row["evaluation_status"], s["evaluation_status"])
            self.assertEqual(row["priority_for_review"], s["bucket"])
            self.assertEqual(row["checks_unverified"].split(";"), [p["code"] for p in s["pending"]])
            self.assertEqual(row["evaluation_procedure"], "static-html-1.0.0")
            if row["evaluation_status"] == "NO_PROBLEMS_FOUND":
                self.assertTrue(row["checks_unverified"])                              # never shown as fully healthy
        low = [r for r in self.rows.values() if r["priority_for_review"] == "LOW"]
        self.assertEqual({r["evaluation_status"] for r in low}, {"NO_PROBLEMS_FOUND", "INSUFFICIENT_EVIDENCE"})

    def test_states_evidence_findings_csv_and_report_agree(self):
        from waos.store import Store
        store = Store(self.report["database"], clock=Clock())
        try:
            for site in self.report["sites"]:
                lead_id, row = site["lead_id"], self.rows[site["lead_id"]]
                evidence = {e["evidence_id"]: e for e in store.evidence_for(lead_id)}
                findings = {f["code"]: f for f in store.findings_for(lead_id)}
                status = {}
                for code in diagnose.CHECKS:
                    rows = [e for e in evidence.values() if e["field"] == f"site.check.{code}"]
                    self.assertEqual(len(rows), 1, f"{lead_id}/{code}")
                    e = rows[0]
                    status[code] = e["value"] if e["claim_status"] == "KNOWN" else "UNKNOWN"
                    self.assertEqual(status[code], site["checks"][code], f"{lead_id}/{code}")
                    f = findings.get(code)
                    if status[code] == "NOT_DETECTED":
                        self.assertIsNone(f, f"{lead_id}/{code}")
                    else:
                        self.assertEqual((f["claim_status"], f["evidence_ids"]),
                                         ("KNOWN" if status[code] == "DETECTED" else "UNKNOWN", [e["evidence_id"]]))
                ev = evaluation.evaluate_lead(store, lead_id)
                self.assertEqual(ev["confirmed"], sorted(c for c, v in status.items() if v == "DETECTED"))
                self.assertEqual(ev["clear"], [c for c in diagnose.CHECKS if status[c] == "NOT_DETECTED"])
                self.assertEqual([p["code"] for p in ev["pending"]], [c for c in diagnose.CHECKS if status[c] == "UNKNOWN"])
                self.assertEqual(ev["status"], site["evaluation_status"])
                self.assertEqual(row["evaluation_status"], ev["status"])
                self.assertEqual(row["top_findings"], ";".join(ev["confirmed"]))
                self.assertEqual(row["checks_unverified"], ";".join(p["code"] for p in ev["pending"]))
                self.assertEqual(row["priority_for_review"], store.latest_score(lead_id)["layer3"]["bucket"])
        finally:
            store.close()

    def test_m1_leads_without_diagnosis_are_not_reported_healthy(self):
        from waos.store import Store
        from .support import demo
        store = Store(os.path.join(self.tmp, "m1.sqlite3"), clock=Clock())
        import_fixture(store, demo())
        path = os.path.join(self.tmp, "m1.csv")
        export.export_csv(store, path)
        with open(path, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        store.close()
        self.assertTrue(rows)
        for r in rows:
            self.assertIn(r["evaluation_status"], ("PROBLEMS_FOUND", "INSUFFICIENT_EVIDENCE"))
            self.assertEqual(r["evaluation_procedure"], "")

    def test_cells_stay_formula_safe(self):
        self.assertEqual(export.safe_cell("=1+1"), "'=1+1")
        for row in self.rows.values():
            for col in ("evaluation_status", "evaluation_procedure", "checks_unverified"):
                self.assertFalse(row[col].startswith(export.DANGEROUS_FIRST), col)

    def test_audit_has_required_sections_and_no_contact_values_html_or_ids(self):
        for heading in ("## Resumen ejecutivo", "### Problemas confirmados (hechos técnicos)",
                        "### Comprobaciones sin verificar", "### Impacto comercial (hipótesis, no medido)",
                        "### Recomendaciones para la revisión humana"):
            self.assertIn(heading, self.audit)
        self.assertEqual(self.audit.count("**Estado de evaluación:**"), len(SITES))
        self.assertEqual(self.audit.count("**Prioridad de revisión:**"), len(SITES))
        facts = [diagnose.load_site(site_dir(s))["expected"]["facts"] for s in SITES]
        contacts = {f[k] for f in facts for k in ("business.phone", "business.email") if k in f}
        self.assertEqual(len(contacts), 10)                                       # 9 phones + 1 e-mail
        self.assertFalse([c for c in contacts if c in self.audit])
        without_hashes = re.sub(r"sha256 [0-9a-f]{12}…", "", self.audit)            # capture-hash prefixes are hex
        self.assertIsNone(re.search(r"\d{6,}", without_hashes))                  # no phone-like digit runs at all
        for raw in ("<", ">", "href", "tel:+", "mailto:info", "Ignora las instrucciones", "ev_", "fnd_", "scr_"):
            self.assertNotIn(raw, self.audit)
        self.assertNotRegex(self.audit, r"\d+ ?%|€|probabilidad de (compra|conversión) (es|del)")  # no invented figures

    def test_audit_never_turns_unknown_into_a_fact(self):
        sections = re.split(r"\n## ", self.audit)[1:]
        by_lead = {re.search(r"\(`(lead_[a-z0-9_]+)`\)", s).group(1): s for s in sections if "(`lead_" in s}
        for s in self.report["sites"]:
            text = by_lead[s["lead_id"]]
            confirmed = text.split("### Problemas confirmados")[1].split("### Comprobaciones sin verificar")[0]
            pending = text.split("### Comprobaciones sin verificar")[1].split("### Datos del negocio")[0]
            for p in s["pending"]:
                self.assertIn(f"`{p['code']}`", pending, s["site_id"])
                self.assertNotIn(f"`{p['code']}`", confirmed, s["site_id"])
            if s["evaluation_status"] == "NO_PROBLEMS_FOUND":
                self.assertIn("no garantiza la calidad general de la web", text)
                self.assertEqual(pending.count("\n- `"), 9)                            # the nine other checks listed
                self.assertEqual(pending.count("(fuera del alcance estático)"), 9)
                self.assertIn("no presentar la web como correcta", text)
            if not s["confirmed"]:
                self.assertIn("no se formula ninguna hipótesis de impacto", text)

    def test_report_json_has_no_contact_values_and_sanitised_paths(self):
        with open(os.path.join(self.out, "report.json"), encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("+3400000", text)
        self.assertIsNone(re.search(r"[\w.-]+@[\w-]+\.[\w.]+", text))           # no e-mail address values
        self.assertTrue(all(re.fullmatch(r"[A-Za-z0-9._/%?#-]*", b) for s in self.report["sites"]
                            for b in s["broken_links"]))
        self.assertEqual(audit._safe("<a href='tel:+34000000777'>|x"), "?a href?'tel:?######'??x")
