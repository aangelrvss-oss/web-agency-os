"""M2a: static diagnosis of the local synthetic corpus. Network blocked (tests/__init__.py); local files only."""
import csv
import os
import shutil
import tempfile

from waos import assessment, diagnose, privacy, workflow
from waos.ingest import import_fixture
from waos.util import ROOT, load_json

from .support import Base, Clock

CORPUS = os.path.join(ROOT, "corpus", "m2a")
SITES = load_json(os.path.join(CORPUS, "corpus.json"))["sites"]
STATIC = ("SEO_BASICS_MISSING", "NO_LOCAL_SIGNALS", "BROKEN_INTERNAL_LINKS")
NEVER_PASS = ("MIXED_CONTENT", "NOT_MOBILE_READY", "NO_MOBILE_CONTACT_PATH", "NO_HTTPS", "TLS_INVALID", "SITE_DOWN",
              "SLOW_MOBILE", "LAYOUT_SHIFT", "A11Y_SERIOUS")


def site_dir(sid):
    return os.path.join(CORPUS, sid)


class Corpus(Base):
    def setUp(self):
        super().setUp()
        self.corpus, fixture = diagnose.corpus_fixture(CORPUS)
        import_fixture(self.store, fixture)

    def diagnose(self, sid):
        manifest = diagnose.load_site(site_dir(sid))
        workflow.transition(self.store, manifest["lead"]["lead_id"], "IDENTITY_RESOLVED", "system")
        diagnose.diagnose(self.store, site_dir(sid))
        return manifest


class Labels(Corpus):
    def test_every_site_matches_its_labels(self):
        for sid in SITES:
            manifest = diagnose.load_site(site_dir(sid))
            out = diagnose.run_checks(site_dir(sid), manifest, self.corpus["campaign"])
            actual = {c: r["status"] for c, r in out["results"].items()}
            self.assertEqual(actual, manifest["expected"]["checks"], sid)

    def test_corpus_has_good_bad_and_ambiguous_cases_with_purposes(self):
        detected, controls = set(), 0
        for sid in SITES:
            manifest = diagnose.load_site(site_dir(sid))
            self.assertTrue(manifest["purpose"].strip(), sid)
            exp = manifest["expected"]["checks"]
            detected |= {c for c, v in exp.items() if v == "DETECTED"}
            controls += sum(1 for c in STATIC if exp[c] == "NOT_DETECTED")
        self.assertGreaterEqual(len(detected), 6)            # every implemented detector has a positive case
        self.assertGreaterEqual(controls, 10)                 # and several false-positive controls

    def test_checks_needing_network_or_browser_never_pass(self):
        for sid in SITES:
            out = diagnose.run_checks(site_dir(sid), diagnose.load_site(site_dir(sid)), self.corpus["campaign"])
            for code in NEVER_PASS:
                self.assertNotEqual(out["results"][code]["status"], "NOT_DETECTED", f"{sid}/{code}")

    def test_threshold_and_truncated_crawl(self):
        manifest = diagnose.load_site(site_dir("s03_broken_mixed"))
        cfg = dict(diagnose.rules(), broken_internal_links_min=4)                 # P-05 is a parameter, not code
        out = diagnose.run_checks(site_dir("s03_broken_mixed"), manifest, self.corpus["campaign"], cfg)
        self.assertEqual(out["results"]["BROKEN_INTERNAL_LINKS"]["status"], "NOT_DETECTED")
        cfg = dict(diagnose.rules(), max_pages=1)
        out = diagnose.run_checks(site_dir("s01_good"), diagnose.load_site(site_dir("s01_good")),
                                  self.corpus["campaign"], cfg)
        self.assertEqual(out["results"]["BROKEN_INTERNAL_LINKS"]["status"], "UNKNOWN")   # unseen pages ≠ pass


class Integration(Corpus):
    def test_evidence_findings_and_events_are_consistent(self):
        for sid in SITES:
            self.diagnose(sid)
        self.assertEqual(self.events_of("evidence.rejected"), [])
        self.assertEqual(len(self.events_of("diagnosis.completed")), len(SITES))
        evidence = {e["evidence_id"]: e for e in self.store.docs("evidence")}
        for f in self.store.docs("findings"):
            self.assertTrue(f["evidence_ids"] and all(i in evidence for i in f["evidence_ids"]), f["code"])
            ev = evidence[f["evidence_ids"][0]]
            if f["claim_status"] == "UNKNOWN":
                self.assertEqual((ev["claim_status"], ev["value"]), ("UNKNOWN", None))
            else:
                self.assertEqual((ev["claim_status"], ev["value"], ev["source_class"]), ("KNOWN", "DETECTED", "MEASUREMENT"))

    def test_site_facts_follow_the_evidence_rules(self):
        for sid in SITES:
            manifest = self.diagnose(sid)
            facts = {e["field"]: e for e in self.store.evidence_for(manifest["lead"]["lead_id"])
                     if not e["field"].startswith("site.check.")}
            self.assertEqual({k: e["value"] for k, e in facts.items()}, manifest["expected"]["facts"], sid)
            for e in facts.values():
                if e["claim_status"] == "KNOWN":
                    self.assertIn(e["snippet"], self.store.capture_text(e["capture_sha256"]))
        s05 = {e["field"]: e for e in self.store.evidence_for("lead_m2a_s05_ambiguous")}
        self.assertEqual(s05["business.municipality"]["claim_status"], "INFERRED")     # plain text is not KNOWN
        phones = [e["value"] for e in self.store.docs("evidence") if e["field"] == "business.phone"]
        self.assertNotIn("+34000000999", phones)                                       # commented-out link ignored

    def test_unknown_findings_raise_the_ceiling_only(self):
        self.diagnose("s01_good")
        workflow.transition(self.store, "lead_m2a_s01_good", "DIAGNOSED", "system")
        score = assessment.score_lead(self.store, "lead_m2a_s01_good")
        self.assertEqual((score["layer1"]["TG"]["floor"], score["layer1"]["TG"]["ceiling"]), (0, 3))
        self.assertEqual((score["layer2"]["IM"]["floor"], score["layer2"]["IM"]["ceiling"]), (0, 3))
        self.assertEqual(score["layer3"]["bucket"], "LOW")                  # not promoted on unverified problems

    def test_rediagnosis_is_refused_and_events_hold_no_contact_values(self):
        self.diagnose("s03_broken_mixed")
        with self.assertRaises(diagnose.DiagnosisError):
            diagnose.diagnose(self.store, site_dir("s03_broken_mixed"))
        phones = {f["business.phone"] for f in (diagnose.load_site(site_dir(s))["expected"]["facts"] for s in SITES)
                  if "business.phone" in f}
        self.assertEqual(privacy.event_leaks(self.store, phones), [])


class LocalFilesOnly(Base):
    def test_links_cannot_read_outside_the_site(self):
        tmp = tempfile.mkdtemp()
        try:
            site = os.path.join(tmp, "site")
            os.makedirs(site)
            with open(os.path.join(tmp, "secret.html"), "w") as f:
                f.write("<html><a href='tel:+34000000666'>x</a></html>")
            os.symlink(os.path.join(tmp, "secret.html"), os.path.join(site, "enlace.html"))
            with open(os.path.join(site, "index.html"), "w") as f:
                f.write('<html><a href="enlace.html">a</a> <a href="https://otro.example/x.html">b</a></html>')
            manifest = {"site_id": "t", "base_url": "https://local.example/"}
            pages, broken, _ = diagnose.crawl(site, manifest, diagnose.rules())
            self.assertEqual(list(pages), ["index.html"])          # the symlink to a file outside is not read
            self.assertEqual(broken, {"enlace.html"})
            self.assertIsNone(diagnose._read(site, "../secret.html", 1000))
            self.assertEqual(diagnose._resolve(site, "https://local.example/", "index.html", "../../secret.html"),
                             ("internal", "secret.html"))          # URL normalization keeps it inside the site
        finally:
            shutil.rmtree(tmp)


class Demo(Base):
    def test_one_command_demo_is_reproducible(self):
        out = os.path.join(self.tmp, "demo")
        first = diagnose.run_demo(CORPUS, out, clock=Clock())
        second = diagnose.run_demo(CORPUS, out, clock=Clock())
        self.assertTrue(first["all_match"])
        strip = lambda r: [{k: v for k, v in s.items()} for s in r["sites"]]
        self.assertEqual(strip(first), strip(second))
        with open(os.path.join(out, "report.json"), encoding="utf-8") as f:
            report_text = f.read()
        phones = {diagnose.load_site(site_dir(s))["expected"]["facts"].get("business.phone") for s in SITES} - {None}
        self.assertTrue(phones)
        self.assertFalse([p for p in phones if p in report_text])          # report files hold no contact values
        with open(first["export"]["path"], encoding="utf-8", newline="") as f:
            rows = {r["lead_id"]: r for r in csv.DictReader(f)}
        self.assertEqual(rows["lead_m2a_s01_good"]["top_findings"], "")   # UNKNOWN findings are not listed
        self.assertEqual(rows["lead_m2a_s03_broken_mixed"]["priority_for_review"], "REVIEW_PRIORITY")
