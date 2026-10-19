"""M1 acceptance tests AT1.1–AT1.12 (docs/roadmap.md § M1). Synthetic data only; network blocked (tests/__init__.py)."""
import contextlib
import copy
import csv
import hashlib
import io
import json
import os
import shutil
import socket
import sqlite3
import tempfile
import unittest
from unittest import mock

from waos import approvals, assessment, budget, cli, privacy, schema, workflow
from waos import evidence as E
from waos.export import ExportRefused, export_csv, safe_cell
from waos.ingest import ImportRejected, import_fixture
from waos.store import STATES, IntegrityError, Store
from waos.util import ROOT, RULES, load_json, sha256_text

from . import NetworkBlocked
from .support import OPERATOR, Base, demo, personal_values


def ev(store, lead_id, eid, field, value, **kw):
    lead = store.lead(lead_id)
    doc = {"schema_version": "waos.evidence.v1", "evidence_id": eid,
           "subject": {"lead_id": lead_id, "entity_key": lead["entity_key"]}, "field": field, "value": value,
           "claim_status": "KNOWN", "source_class": "OFFICIAL", "evidence_origin": "FIRST_PARTY_WEB",
           "method": {"tool": "fixture", "tool_version": "m1", "procedure_id": "TEST"},
           "retrieved_at": store.now(), "confidence": "HIGH", "proposed_by": "fixture", "personal_data": "NONE",
           "source_url": "https://example.example/", "snippet": None, "data_mode": "SYNTHETIC"}
    doc.update(kw)
    return doc


def capture_sha(ref):
    return sha256_text(demo()["captures"][ref])


class AT1_1_EvidenceNotInvented(Base):
    def setUp(self):
        super().setUp()
        self.load_demo()
        self.cap = capture_sha("cap_01")

    def reasons(self, eid):
        return [e["payload"]["reasons"] for e in self.events_of("evidence.rejected")
                if e["payload"]["evidence_id"] == eid][0]

    def test_snippet_not_in_capture_is_rejected_and_not_stored(self):
        doc = ev(self.store, "lead_demo_01", "ev_t_bad_snippet", "business.category", "renovation",
                 capture_sha256=self.cap, snippet="Texto que no aparece en la captura")
        self.assertFalse(E.record(self.store, doc))
        self.assertIsNone(self.store.doc("evidence", "evidence_id", "ev_t_bad_snippet"))
        self.assertEqual(self.reasons("ev_t_bad_snippet"), ["SNIPPET_NOT_IN_CAPTURE"])

    def test_known_without_source_url_fails_schema(self):
        doc = ev(self.store, "lead_demo_01", "ev_t_no_url", "business.category", "renovation",
                 capture_sha256=self.cap, snippet="Reformas integrales", source_url=None, capture_available=True,
                 erased=False)
        self.assertTrue(schema.errors_for(schema.contract("evidence"), doc))
        self.assertFalse(E.record(self.store, doc))
        self.assertTrue(any(r.startswith("SCHEMA:/source_url") for r in self.reasons("ev_t_no_url")))

    def test_contact_value_must_appear_literally(self):
        doc = ev(self.store, "lead_demo_01", "ev_t_phone", "business.phone", "+34 000 000 999",
                 personal_data="BUSINESS_CONTACT", capture_sha256=self.cap, snippet="Llámenos al +34 000 000 101")
        self.assertFalse(E.record(self.store, doc))
        self.assertIn("CONTACT_NOT_LITERAL", self.reasons("ev_t_phone"))

    def test_search_snippets_and_inferences_are_never_known(self):
        a = ev(self.store, "lead_demo_01", "ev_t_serp", "business.category", "renovation", capture_sha256=self.cap,
               snippet="Reformas integrales", seen_in="SEARCH_SNIPPET")
        b = ev(self.store, "lead_demo_01", "ev_t_infer", "business.category", "renovation", capture_sha256=self.cap,
               snippet="Reformas integrales", kind="INFERENCE")
        self.assertFalse(E.record(self.store, a))
        self.assertFalse(E.record(self.store, b))
        self.assertIn("SEARCH_SNIPPET_NOT_KNOWN", self.reasons("ev_t_serp"))
        self.assertIn("INFERENCE_NOT_KNOWN", self.reasons("ev_t_infer"))

    def test_incompatible_known_values_resolve_to_conflicting(self):
        status, value, ids = E.resolve(self.store.evidence_for("lead_demo_10"), "business.municipality")
        self.assertEqual((status, value, len(ids)), ("CONFLICTING", None, 2))

    def test_blank_snippets_and_invalid_dates_are_rejected(self):
        a = ev(self.store, "lead_demo_01", "ev_t_blank", "business.category", "renovation", capture_sha256=self.cap,
               snippet=" ")
        b = ev(self.store, "lead_demo_01", "ev_t_date", "business.activity_dated", "reciente", capture_sha256=self.cap,
               snippet="Última obra entregada el 2026-09-15")
        self.assertFalse(E.record(self.store, a))
        self.assertFalse(E.record(self.store, b))
        self.assertIn("SNIPPET_REQUIRED", self.reasons("ev_t_blank"))
        self.assertIn("INVALID_DATE_VALUE", self.reasons("ev_t_date"))

    def test_subject_must_be_an_existing_lead_and_ids_unique(self):
        base = dict(capture_sha256=self.cap, snippet="Reformas integrales")
        cases = {"ev_t_mismatch": ev(self.store, "lead_demo_01", "ev_t_mismatch", "business.category", "renovation",
                                     subject={"lead_id": "lead_demo_01", "entity_key": "otro.example"}, **base),
                 "ev_t_nolead": ev(self.store, "lead_demo_01", "ev_t_nolead", "business.category", "renovation",
                                   subject={"lead_id": "lead_missing", "entity_key": "x.example"}, **base),
                 "ev_demo_01_02": ev(self.store, "lead_demo_01", "ev_demo_01_02", "business.category", "plumbing", **base)}
        for eid, doc in cases.items():
            self.assertFalse(E.record(self.store, doc))          # rejected and recorded, not a crash
        self.assertEqual(self.reasons("ev_t_mismatch"), ["SUBJECT_MISMATCH"])
        self.assertEqual(self.reasons("ev_t_nolead"), ["LEAD_NOT_FOUND"])
        self.assertEqual(self.reasons("ev_demo_01_02"), ["DUPLICATE_EVIDENCE_ID"])
        self.assertEqual(self.store.doc("evidence", "evidence_id", "ev_demo_01_02")["value"], "renovation")

    def test_declared_strength_is_ignored(self):
        doc = ev(self.store, "lead_demo_01", "ev_t_strength", "activity.signal.extra", True, capture_sha256=self.cap,
                 snippet="cocinas y baños", source_class="OTHER_VERIFIABLE", strength="HIGH")
        self.assertTrue(E.record(self.store, doc))
        self.assertEqual(self.store.doc("evidence", "evidence_id", "ev_t_strength")["strength"], "LOW")


class AT1_2_GuardedTransitions(Base):
    def test_skipping_states_is_rejected_without_change(self):
        self.load_demo()
        before = self.store.lead("lead_demo_01")
        with self.assertRaises(workflow.TransitionDenied) as cm:
            workflow.transition(self.store, "lead_demo_01", "SHORTLISTED", "system")
        self.assertEqual(cm.exception.reason, "NOT_ALLOWED")
        after = self.store.lead("lead_demo_01")
        self.assertEqual((after["state"], after["state_version"]), (before["state"], before["state_version"]))
        denied = self.events_of("state.transition_denied", "lead_demo_01")
        self.assertEqual(denied[-1]["payload"], {"from": "DISCOVERED", "to": "SHORTLISTED", "reason": "NOT_ALLOWED"})

    def test_valid_path_emits_one_event_per_step(self):
        self.load_demo()
        self.to_scored("lead_demo_01")
        approval_id, _ = self.shortlist_approval("lead_demo_01")
        workflow.transition(self.store, "lead_demo_01", "SHORTLISTED", OPERATOR, approval_id=approval_id)
        steps = [(e["payload"]["from"], e["payload"]["to"]) for e in self.events_of("state.transitioned", "lead_demo_01")]
        self.assertEqual(steps, [("DISCOVERED", "IDENTITY_RESOLVED"), ("IDENTITY_RESOLVED", "DIAGNOSED"),
                                 ("DIAGNOSED", "SCORED"), ("SCORED", "SHORTLISTED")])
        self.assertEqual(self.store.lead("lead_demo_01")["state_version"], 4)


class AT1_3_UnknownNeverPassesDeterminism(Base):
    def test_unknown_gate_gives_pending(self):
        self.load_demo()
        score = assessment.score_lead(self.store, "lead_demo_03")
        gates = {g["gate_id"]: g["result"] for g in score["gates"]}
        self.assertEqual(gates["G_GEO"], "UNKNOWN")
        self.assertEqual(score["layer3"]["bucket"], "PENDING")

    def test_future_activity_date_does_not_pass(self):
        self.load_demo()
        rows = [dict(e, value="2030-01-01") if e["field"] == "business.activity_dated" else e
                for e in self.store.evidence_for("lead_demo_01")]
        score = assessment.assess(self.store.lead("lead_demo_01"), self.store.campaign("cmp_demo"), rows,
                                  self.store.findings_for("lead_demo_01"), self.clock())
        self.assertEqual({g["gate_id"]: g["result"] for g in score["gates"]}["G_ACTIVE"], "UNKNOWN")
        self.assertEqual(score["layer3"]["bucket"], "PENDING")

    def test_same_inputs_same_record_and_hash(self):
        self.load_demo()
        args = (self.store.lead("lead_demo_01"), self.store.campaign("cmp_demo"),
                self.store.evidence_for("lead_demo_01"), self.store.findings_for("lead_demo_01"), self.clock())
        a, b = assessment.assess(*args), assessment.assess(*args)
        strip = lambda r: {k: v for k, v in r.items() if k not in ("score_id", "computed_at")}
        self.assertEqual(strip(a), strip(b))
        self.assertEqual(a["rules_hash"], b["rules_hash"])

    def test_editing_a_rules_file_changes_the_hash(self):
        original = assessment.rules_hash(assessment.load_rules())
        tmp = tempfile.mkdtemp()
        try:
            for name in os.listdir(RULES):
                shutil.copy(os.path.join(RULES, name), tmp)
            path = os.path.join(tmp, "scoring.v1.json")
            data = load_json(path)
            data["buckets"]["REVIEW_PRIORITY"]["AC_floor_min"] = 2
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            with mock.patch("waos.assessment.RULES", tmp):
                self.assertNotEqual(assessment.rules_hash(assessment.load_rules()), original)
        finally:
            shutil.rmtree(tmp)


class AT1_4_ZeroSpendZeroNetwork(Base):
    def test_priced_unknown_and_unlisted_tools_are_denied(self):
        cases = {"fake.priced_lookup": "PAID_CALLS_DISABLED", "fake.unpriced_lookup": "UNKNOWN_PRICE",
                 "real.web_fetch": "TOOL_NOT_ALLOWED"}
        for tool, reason in cases.items():
            status, detail, entry = budget.call_tool(self.store, tool, {"q": 1}, "run1")
            self.assertEqual((status, detail), ("DENIED", reason))
            row = self.store.doc("ledger", "entry_id", entry["entry_id"])
            self.assertEqual((row["status"], row["deny_reason"], row["actual_cents"]), ("DENIED", reason, 0))
        self.assertEqual(len(self.events_of("tool.call_denied")), 3)
        self.assertEqual(budget.call_tool(self.store, "fake.free_lookup", {}, "run1")[0], "OK")

    def test_shipped_switch_is_off_in_both_places(self):
        self.assertIs(budget.PAID_CALLS_ENABLED, False)
        self.assertIs(budget.load_config()["paid_calls_enabled"], False)
        self.assertFalse(budget.paid_calls_enabled())

    def test_network_lock_is_active(self):
        with self.assertRaises(NetworkBlocked):
            socket.create_connection(("127.0.0.1", 9))
        with self.assertRaises(NetworkBlocked):
            socket.getaddrinfo("example.com", 443)
        from . import ATTEMPTS
        del ATTEMPTS[-2:]                                   # deliberate attempts in this test only

    def test_no_network_modules_in_product_code(self):
        import re
        banned = re.compile(r"^\s*(import|from)\s+(socket|ssl|urllib\.request|http\.client|http\.server|requests"
                            r"|ftplib|smtplib|subprocess|asyncio)\b|^\s*from\s+urllib\s+import\s+request", re.M)
        for name in os.listdir(os.path.join(ROOT, "waos")):        # urllib.parse (pure string parsing) is allowed
            if name.endswith(".py"):
                with open(os.path.join(ROOT, "waos", name), encoding="utf-8") as f:
                    self.assertIsNone(banned.search(f.read()), f"{name} imports a network-capable module")


class AT1_5_AppendOnlyTraceableLog(Base):
    def test_update_and_delete_on_events_fail(self):
        self.load_demo()
        with self.assertRaises(sqlite3.DatabaseError):
            self.store.conn.execute("UPDATE events SET type='x'")
        with self.assertRaises(sqlite3.DatabaseError):
            self.store.conn.execute("DELETE FROM events")

    def test_trace_lists_all_events_including_rejections(self):
        self.load_demo()
        with contextlib.suppress(workflow.TransitionDenied):
            workflow.transition(self.store, "lead_demo_01", "SHORTLISTED", "system")
        workflow.transition(self.store, "lead_demo_01", "IDENTITY_RESOLVED", "system")
        self.store.close()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["--db", self.db, "trace", "lead_demo_01"]), 0)
        self.store = Store(self.db, clock=self.clock)
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), len(self.store.events("lead_demo_01")))
        seqs = [int(line.split()[0]) for line in lines]
        self.assertEqual(seqs, sorted(seqs))
        self.assertTrue(any("state.transition_denied" in line for line in lines))
        self.assertTrue(any("state.transitioned" in line for line in lines))

    def test_missing_trigger_refuses_to_run(self):
        self.store.close()
        raw = sqlite3.connect(self.db)
        raw.execute("DROP TRIGGER events_no_delete")
        raw.commit()
        raw.close()
        with self.assertRaises(IntegrityError):
            Store(self.db)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(cli.main(["--db", self.db, "verify"]), 2)
        self.assertIn("missing trigger events_no_delete", err.getvalue())
        raw = sqlite3.connect(self.db)                          # repair only for tearDown
        raw.execute("CREATE TRIGGER events_no_delete BEFORE DELETE ON events "
                    "BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;")
        raw.commit()
        raw.close()
        self.store = Store(self.db, clock=self.clock)


class AT1_6_InvalidTransitionsExhaustive(Base):
    def test_every_pair_not_in_the_table_is_rejected(self):
        self.load_demo()
        rules, terminal = workflow.table()
        lead_id = "lead_demo_09"
        rejected = 0
        for frm in STATES:
            for to in STATES:
                lead = self.store.lead(lead_id)
                lead["state"], lead["on_hold_from"] = frm, ("SCORED" if frm == "ON_HOLD" else None)
                with self.store.tx():
                    self.store.put_lead(lead)
                allowed = (frm, to) in rules or (frm == "ON_HOLD" and to == "SCORED")
                if allowed:
                    continue
                before = self.store.lead(lead_id)
                with self.assertRaises(workflow.TransitionDenied):
                    workflow.transition(self.store, lead_id, to, OPERATOR)
                after = self.store.lead(lead_id)
                self.assertEqual((after["state"], after["state_version"]), (before["state"], before["state_version"]))
                rejected += 1
        self.assertGreater(rejected, 60)
        self.assertEqual(rejected, len(self.events_of("state.transition_denied", lead_id)))

    def test_terminal_states_have_no_outgoing_transition(self):
        rules, terminal = workflow.table()
        self.assertEqual(terminal, {"DISQUALIFIED", "SUPPRESSED"})
        self.assertFalse([k for k in rules if k[0] in terminal])

    def test_unknown_state_and_guard_failures(self):
        self.load_demo()
        with self.assertRaises(workflow.TransitionDenied) as cm:
            workflow.transition(self.store, "lead_demo_01", "WON", "system")
        self.assertEqual(cm.exception.reason, "UNKNOWN_STATE")
        self.to_scored("lead_demo_04")                          # bucket WATCH
        with self.assertRaises(workflow.TransitionDenied) as cm:
            workflow.transition(self.store, "lead_demo_04", "SHORTLISTED", OPERATOR)
        self.assertEqual(cm.exception.reason, "GUARD_FAILED:review_priority_and_shortlist_approval")
        self.to_scored("lead_demo_01")                          # REVIEW_PRIORITY, no approval
        with self.assertRaises(workflow.TransitionDenied) as cm:
            workflow.transition(self.store, "lead_demo_01", "SHORTLISTED", OPERATOR)
        self.assertEqual(cm.exception.reason, "APPROVAL_REQUIRED")
        with self.assertRaises(workflow.TransitionDenied) as cm:
            workflow.transition(self.store, "lead_demo_04", "ON_HOLD", "system")   # not a human decision
        self.assertEqual(cm.exception.reason, "GUARD_FAILED:human_decision")

    def test_stale_version_only_first_attempt_succeeds(self):
        self.load_demo()
        version = self.store.lead("lead_demo_01")["state_version"]
        workflow.transition(self.store, "lead_demo_01", "IDENTITY_RESOLVED", "system", expected_version=version)
        with self.assertRaises(workflow.TransitionDenied) as cm:
            workflow.transition(self.store, "lead_demo_01", "DIAGNOSED", "system", expected_version=version)
        self.assertEqual(cm.exception.reason, "STALE_VERSION")


class AT1_7_ApprovalBoundToExactHash(Base):
    def setUp(self):
        super().setUp()
        self.load_demo()
        self.to_scored("lead_demo_01")

    def test_executes_once(self):
        approval_id, action = self.shortlist_approval("lead_demo_01")
        workflow.transition(self.store, "lead_demo_01", "SHORTLISTED", OPERATOR, approval_id=approval_id)
        self.assertEqual(approvals.check(self.store, approval_id, action, "SHORTLIST"), "ALREADY_EXECUTED")
        doc = approvals.get(self.store, approval_id)
        self.assertEqual((doc["status"], doc["execution_count"]), ("EXECUTED", 1))
        b = approvals.request(self.store, "BUDGET_CHANGE", budget.change_action(100, 10), "system")
        approvals.decide(self.store, b["approval_id"], "APPROVED", OPERATOR)
        budget.apply_change(self.store, b["approval_id"], 100, 10, OPERATOR)
        with self.assertRaises(approvals.ApprovalError) as cm:
            budget.apply_change(self.store, b["approval_id"], 100, 10, OPERATOR)
        self.assertEqual(cm.exception.reason, "ALREADY_EXECUTED")

    def test_any_change_to_the_action_is_rejected(self):
        approval_id, action = self.shortlist_approval("lead_demo_01")
        for changed in ({**action, "lead_id": "lead_demo_02"}, {**action, "score_id": "scr_other"},
                        {**action, "extra": 1}):
            self.assertEqual(approvals.check(self.store, approval_id, changed, "SHORTLIST"), "HASH_MISMATCH")
        self.tick()
        assessment.score_lead(self.store, "lead_demo_01")          # a newer score changes the action to execute
        with self.assertRaises(workflow.TransitionDenied) as cm:
            workflow.transition(self.store, "lead_demo_01", "SHORTLISTED", OPERATOR, approval_id=approval_id)
        self.assertEqual(cm.exception.reason, "APPROVAL:HASH_MISMATCH")
        self.assertEqual(self.store.lead("lead_demo_01")["state"], "SCORED")

    def test_expired_approval_is_rejected(self):
        approval_id, action = self.shortlist_approval("lead_demo_01")
        self.clock.advance(hours=169)
        self.assertEqual(approvals.check(self.store, approval_id, action, "SHORTLIST"), "EXPIRED")
        pending = approvals.request(self.store, "SHORTLIST", action, "system")
        self.clock.advance(hours=169)
        with self.assertRaises(approvals.ApprovalError) as cm:
            approvals.decide(self.store, pending["approval_id"], "APPROVED", OPERATOR)
        self.assertEqual(cm.exception.reason, "EXPIRED")

    def test_only_humans_decide_and_rejected_cannot_execute(self):
        score = self.store.latest_score("lead_demo_01")
        action = {"kind": "SHORTLIST", "lead_id": "lead_demo_01", "score_id": score["score_id"]}
        doc = approvals.request(self.store, "SHORTLIST", action, "system")
        for actor in ("system", "agent:planner"):
            with self.assertRaises(approvals.ApprovalError) as cm:
                approvals.decide(self.store, doc["approval_id"], "APPROVED", actor)
            self.assertEqual(cm.exception.reason, "DECIDER_NOT_HUMAN")
        approvals.decide(self.store, doc["approval_id"], "REJECTED", OPERATOR)
        self.assertEqual(approvals.check(self.store, doc["approval_id"], action, "SHORTLIST"), "NOT_APPROVED:REJECTED")
        with self.assertRaises(workflow.TransitionDenied):
            workflow.transition(self.store, "lead_demo_01", "SHORTLISTED", OPERATOR, approval_id=doc["approval_id"])

    def test_stale_pre_check_cannot_execute_twice(self):
        b = approvals.request(self.store, "BUDGET_CHANGE", budget.change_action(100, 10), "system")
        approvals.decide(self.store, b["approval_id"], "APPROVED", OPERATOR)
        with mock.patch("waos.approvals.check", return_value=None):  # every check is stale: only the atomic
            budget.apply_change(self.store, b["approval_id"], 100, 10, OPERATOR)     # conditional update can stop it
            with self.assertRaises(approvals.ApprovalError) as cm:
                budget.apply_change(self.store, b["approval_id"], 100, 10, OPERATOR)
        self.assertEqual(cm.exception.reason, "ALREADY_EXECUTED")
        self.assertEqual(len(self.events_of("approval.executed")), 1)

    def test_stale_read_cannot_overwrite_a_decision(self):
        approval_id, action = self.shortlist_approval("lead_demo_01")
        stale = dict(approvals.get(self.store, approval_id), status="PENDING", decision=None)
        with mock.patch("waos.approvals.get", return_value=stale):
            with self.assertRaises(approvals.ApprovalError) as cm:
                approvals.decide(self.store, approval_id, "REJECTED", "human:other")
        self.assertEqual(cm.exception.reason, "NOT_PENDING:CHANGED")
        self.assertEqual(approvals.get(self.store, approval_id)["status"], "APPROVED")

    def test_type_mismatch_and_canonical_hash(self):
        b = approvals.request(self.store, "BUDGET_CHANGE", budget.change_action(100, 10), "system")
        approvals.decide(self.store, b["approval_id"], "APPROVED", OPERATOR)
        with self.assertRaises(workflow.TransitionDenied) as cm:
            workflow.transition(self.store, "lead_demo_01", "SHORTLISTED", OPERATOR, approval_id=b["approval_id"])
        self.assertEqual(cm.exception.reason, "APPROVAL:TYPE_MISMATCH")
        self.assertEqual(approvals.action_hash({"kind": "X", "a": 1, "b": [1, 2]}),
                         approvals.action_hash({"b": [1, 2], "a": 1, "kind": "X"}))


class AT1_8_DataProtection(Base):
    def test_real_data_is_rejected_without_values_in_events(self):
        for fixture in (dict(demo(), data_mode="REAL"), demo()):
            if fixture["data_mode"] != "REAL":
                fixture["leads"][0]["evidence"][0]["data_mode"] = "REAL"
            with self.assertRaises(ImportRejected):
                import_fixture(self.store, fixture)
        self.assertEqual(self.store.conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0], 0)
        for e in self.events_of("import.rejected"):
            self.assertEqual(e["payload"], {"reason": "DATA_MODE_NOT_ALLOWED_IN_M1"})

    def test_full_scenario_leaves_no_personal_values_in_events(self):
        self.load_demo()
        self.to_scored("lead_demo_01")
        self.to_scored("lead_demo_02")
        approval_id, _ = self.shortlist_approval("lead_demo_02")
        workflow.transition(self.store, "lead_demo_02", "SHORTLISTED", OPERATOR, approval_id=approval_id)
        export_csv(self.store, os.path.join(self.tmp, "x.csv"))
        privacy.suppress(self.store, "lead_demo_02", "OPT_OUT", OPERATOR)
        privacy.erase(self.store, "lead_demo_01", OPERATOR)
        self.clock.advance(days=400)
        privacy.retention_run(self.store, "system")
        values = personal_values()
        self.assertGreaterEqual(len(values), 5)
        self.assertEqual(privacy.event_leaks(self.store, values), [])

    def test_suppression_blocks_transitions_erases_and_blocks_reimport(self):
        self.load_demo()
        self.to_scored("lead_demo_02")
        privacy.suppress(self.store, "lead_demo_02", "OPT_OUT", OPERATOR)
        lead = self.store.lead("lead_demo_02")
        self.assertEqual((lead["state"], lead["suppressed"]), ("SUPPRESSED", True))
        self.assertIsNone(lead["business"]["phone"])
        with self.assertRaises(workflow.TransitionDenied) as cm:
            workflow.transition(self.store, "lead_demo_02", "PARKED", OPERATOR)
        self.assertEqual(cm.exception.reason, "TERMINAL_STATE")
        for e in self.store.evidence_for("lead_demo_02"):
            if e["personal_data"] != "NONE":
                self.assertEqual((e["value"], e["snippet"], e["erased"]), (None, None, True))
        again = demo()
        entry = copy.deepcopy([x for x in again["leads"] if x["lead"]["lead_id"] == "lead_demo_02"][0])
        entry["lead"]["lead_id"] = "lead_demo_02_again"
        entry["lead"]["entity_key"] = entry["lead"]["business"]["domain"] = "otro-dominio.example"
        entry["evidence"] = []
        again["leads"], again["captures"] = [entry], {}
        summary = import_fixture(self.store, again)           # same phone/email, different domain
        self.assertEqual((summary["leads_imported"], summary["leads_rejected"]), (0, 1))
        self.assertEqual(self.events_of("import.rejected")[-1]["payload"]["reason"], "SUPPRESSED_IDENTIFIER")

    def test_erasure_keeps_ids_and_hashes(self):
        self.load_demo()
        erased = privacy.erase(self.store, "lead_demo_02", OPERATOR)
        self.assertEqual(len(erased), 3)
        for e in self.store.evidence_for("lead_demo_02"):
            if e["evidence_id"] in erased:
                self.assertEqual((e["value"], e["snippet"], e["erased"]), (None, None, True))
                self.assertRegex(e["capture_sha256"], "^[0-9a-f]{64}$")
            self.assertFalse(e["capture_available"])          # capture text removed with the personal data (E6)
        self.assertIsNone(self.store.capture_text(capture_sha("cap_02")))
        payload = self.events_of("evidence.erased", "lead_demo_02")[-1]["payload"]
        self.assertEqual(sorted(payload["evidence_ids"]), sorted(erased))

    def test_retention_purges_expired_personal_values(self):
        with mock.patch("waos.evidence.retention_days", return_value={"BUSINESS_CONTACT": 2, "OTHER": 2}):
            self.load_demo()                                   # synthetic duration: 2 days
        self.clock.advance(days=1)
        self.assertEqual(privacy.retention_run(self.store, "system"), [])
        self.clock.advance(days=2)
        purged = privacy.retention_run(self.store, "system")
        self.assertEqual(len(purged), 4)                       # lead 01: phone; lead 02: owner name, email, phone
        self.assertTrue(all(self.store.doc("evidence", "evidence_id", i)["erased"] for i in purged))
        self.assertEqual(self.events_of("retention.purged")[-1]["payload"]["count"], len(purged))

    def test_retention_also_clears_contact_fields_held_on_the_lead(self):
        self.load_demo()                                   # lead 11 has a phone on the lead and no phone evidence
        self.assertIsNotNone(self.store.lead("lead_demo_11")["business"]["phone"])
        with mock.patch("waos.evidence.retention_days", return_value={"BUSINESS_CONTACT": 2, "OTHER": 2}):
            self.clock.advance(days=1)
            privacy.retention_run(self.store, "system")
            self.assertIsNotNone(self.store.lead("lead_demo_11")["business"]["phone"])
            self.clock.advance(days=2)
            privacy.retention_run(self.store, "system")
        self.assertIsNone(self.store.lead("lead_demo_11")["business"]["phone"])
        self.assertIn("lead_demo_11", self.events_of("retention.purged")[-1]["payload"]["lead_ids_cleared"])


class AT1_9_ExportSafety(Base):
    def setUp(self):
        super().setUp()
        self.load_demo()
        for lead_id in ("lead_demo_01", "lead_demo_02", "lead_demo_11"):
            self.to_scored(lead_id)
        privacy.suppress(self.store, "lead_demo_02", "OPT_OUT", OPERATOR)
        self.path = os.path.join(self.tmp, "leads_SYNTHETIC.csv")
        self.result = export_csv(self.store, self.path)
        with open(self.path, encoding="utf-8", newline="") as f:
            self.rows = list(csv.DictReader(f))
        self.by_id = {r["lead_id"]: r for r in self.rows}

    def test_dangerous_first_characters_are_escaped(self):
        for ch in ("=", "+", "-", "@", "\t", "\r", "\n", "＝", "＋", "－", "＠"):
            self.assertEqual(safe_cell(ch + "x"), "'" + ch + "x")
        self.assertEqual(safe_cell("normal"), "normal")
        row = self.by_id["lead_demo_11"]
        original = [x for x in demo()["leads"] if x["lead"]["lead_id"] == "lead_demo_11"][0]["lead"]["business"]
        self.assertEqual(row["business_name"], "'" + original["name"])      # commas, quotes, newline round-trip
        self.assertEqual(row["website"], "'" + original["website_url"])
        self.assertEqual(row["business_phone"], "'" + original["phone"])
        for r in self.rows:
            for value in r.values():
                self.assertFalse(value.startswith(("=", "+", "-", "@")), value)

    def test_contact_hidden_for_suppressed_and_columns_are_honest(self):
        self.assertEqual(self.by_id["lead_demo_02"]["business_phone"], "")
        self.assertEqual(self.by_id["lead_demo_02"]["suppressed"], "true")
        header = list(self.rows[0].keys())
        self.assertIn("priority_for_review", header)
        self.assertEqual([h for h in header if "intent" in h or "interest" in h], ["purchase_intent"])
        self.assertEqual({r["purchase_intent"] for r in self.rows}, {"UNKNOWN"})

    def test_export_event_matches_file_without_values(self):
        payload = self.events_of("export.created")[-1]["payload"]
        with open(self.path, "rb") as f:
            self.assertEqual(payload["sha256"], hashlib.sha256(f.read()).hexdigest())
        self.assertEqual(payload["row_count"], len(self.rows))
        self.assertEqual(set(payload), {"file_name", "sha256", "row_count", "columns"})

    def test_real_records_are_refused(self):
        lead = self.store.lead("lead_demo_01")
        lead["data_mode"] = "REAL"
        with mock.patch.object(self.store, "docs", return_value=[lead]):
            with self.assertRaises(ExportRefused):
                export_csv(self.store, os.path.join(self.tmp, "real.csv"))
        self.assertEqual(self.events_of("export.refused")[-1]["payload"]["reason"], "REAL_DATA_NOT_ALLOWED_IN_M1")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "real.csv")))


class AT1_10_TechnicalScoreIsNotIntent(Base):
    def setUp(self):
        super().setUp()
        self.load_demo()

    def assess(self, lead_id, rules=None):
        return assessment.assess(self.store.lead(lead_id), self.store.campaign("cmp_demo"),
                                 self.store.evidence_for(lead_id), self.store.findings_for(lead_id), self.clock(), rules)

    def test_technical_severity_alone_never_promotes(self):
        rules = assessment.load_rules()
        rules["impact_rules.v1.json"]["impact"].update(NO_MOBILE_CONTACT_PATH="LOW", SLOW_MOBILE="LOW")
        score = self.assess("lead_demo_01", rules)
        self.assertEqual(score["layer1"]["TG"]["floor"], 3)
        self.assertEqual(score["layer2"]["IM"]["floor"], 1)
        self.assertEqual(score["layer3"]["bucket"], "WATCH")
        self.assertEqual(self.assess("lead_demo_01")["layer3"]["bucket"], "REVIEW_PRIORITY")   # control

    def test_unknown_value_band_and_contraindication_block_priority(self):
        s4 = self.assess("lead_demo_04")
        self.assertEqual((s4["layer2"]["IM"]["floor"], s4["layer3"]["BV"]["floor"], s4["layer3"]["BV"]["ceiling"]),
                         (3, 0, 3))
        self.assertEqual(s4["layer3"]["bucket"], "WATCH")
        s5 = self.assess("lead_demo_05")
        self.assertEqual(s5["layer3"]["contraindications"][0]["claim_status"], "KNOWN")
        self.assertEqual(s5["layer3"]["bucket"], "WATCH")

    def test_purchase_intent_cannot_change(self):
        self.to_scored("lead_demo_01")
        for lead in self.store.docs("leads"):
            self.assertEqual(lead["purchase_intent"], "UNKNOWN")
        lead = self.store.lead("lead_demo_01")
        lead["purchase_intent"] = "INTERESTED"
        with self.assertRaises(schema.ValidationError):
            self.store.put_lead(lead)
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.conn.execute("UPDATE leads SET purchase_intent='INTERESTED' WHERE lead_id='lead_demo_01'")

    def test_review_priority_waits_for_a_human(self):
        self.to_scored("lead_demo_01")
        self.assertEqual(self.store.latest_score("lead_demo_01")["layer3"]["bucket"], "REVIEW_PRIORITY")
        self.assertEqual(self.store.lead("lead_demo_01")["state"], "SCORED")
        with self.assertRaises(workflow.TransitionDenied):
            workflow.transition(self.store, "lead_demo_01", "SHORTLISTED", "system")
        self.assertEqual(self.store.lead("lead_demo_01")["state"], "SCORED")


class AT1_11_BudgetRules(Base):
    """Uses injected configuration (patched constant + explicit config), never the shipped configuration."""
    CONFIG = {"paid_calls_enabled": True}

    def call(self, tool, run):
        return budget.call_tool(self.store, tool, {}, run, config=self.CONFIG)

    def set_caps(self, g, r):
        doc = approvals.request(self.store, "BUDGET_CHANGE", budget.change_action(g, r), "system")
        approvals.decide(self.store, doc["approval_id"], "APPROVED", OPERATOR)
        budget.apply_change(self.store, doc["approval_id"], g, r, OPERATOR)

    def test_caps_reservations_and_ledger(self):
        with mock.patch("waos.budget.PAID_CALLS_ENABLED", True):
            self.assertEqual(self.call("fake.priced_lookup", "r1")[:2], ("DENIED", "NO_BUDGET"))
            self.set_caps(20, 12)
            self.assertEqual(self.call("fake.priced_lookup", "r1")[0], "OK")                 # spent 5
            self.assertEqual(self.call("fake.discounted_lookup", "r1")[:2], ("DENIED", "CAP_EXCEEDED"))  # run 15 > 12
            status, _, entry = self.call("fake.discounted_lookup", "r2")                       # reserve 10, actual 4
            self.assertEqual((status, entry["reserved_cents"], entry["actual_cents"]), ("OK", 10, 4))
            self.assertEqual(self.call("fake.discounted_lookup", "r3")[0], "OK")              # 9 + 10 <= 20
            self.assertEqual(self.call("fake.discounted_lookup", "r4")[:2], ("DENIED", "CAP_EXCEEDED"))  # 13 + 10 > 20
        ok = [d for d in self.store.docs("ledger") if d["status"] == "OK"]
        self.assertEqual(sum(d["actual_cents"] for d in ok), 13)
        self.assertEqual(budget.spent(self.store), 13)
        self.assertEqual(budget.status(self.store)["remaining_cents"], 7)

    def test_caps_change_only_with_matching_executed_approval(self):
        with self.assertRaises(approvals.ApprovalError) as cm:
            budget.apply_change(self.store, "apr_missing", 50, 5, OPERATOR)
        self.assertEqual(cm.exception.reason, "NOT_FOUND")
        doc = approvals.request(self.store, "BUDGET_CHANGE", budget.change_action(50, 5), "system")
        approvals.decide(self.store, doc["approval_id"], "APPROVED", OPERATOR)
        with self.assertRaises(approvals.ApprovalError) as cm:
            budget.apply_change(self.store, doc["approval_id"], 5000, 5, OPERATOR)
        self.assertEqual(cm.exception.reason, "HASH_MISMATCH")
        self.assertIsNone(budget.caps(self.store))


class AT1_12_ContractAndStorageIntegrity(Base):
    def test_contract_cases(self):
        cases = load_json(os.path.join(ROOT, "tests", "fixtures", "contract_cases.json"))
        self.assertEqual(set(cases), set(schema.CONTRACT_NAMES))
        for name, c in cases.items():
            self.assertGreaterEqual(len(c["valid"]), 3, name)
            self.assertGreaterEqual(len(c["invalid"]), 3, name)
            for doc in c["valid"]:
                self.assertEqual(schema.errors_for(schema.contract(name), doc), [], name)
            for doc in c["invalid"]:
                self.assertTrue(schema.errors_for(schema.contract(name), doc), f"{name}: invalid case accepted")

    def test_unsupported_schema_keyword_is_an_error(self):
        with self.assertRaises(ValueError):
            schema.errors_for({"type": "string", "format": "email"}, "x")

    def test_foreign_keys_and_checks_are_enforced_by_the_database(self):
        self.load_demo()
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.conn.execute("INSERT INTO findings(finding_id, lead_id, code, technical_severity, claim_status, doc)"
                                    " VALUES ('fnd_x', 'lead_missing', 'NO_HTTPS', 'MAJOR', 'KNOWN', '{}')")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.conn.execute("UPDATE leads SET state='WON' WHERE lead_id='lead_demo_01'")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.conn.execute("UPDATE leads SET data_mode='REAL' WHERE lead_id='lead_demo_01'")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.conn.execute("UPDATE evidence SET claim_status='MAYBE'")

    def test_triggers_survive_repeated_migrations(self):
        self.store.migrate()
        self.store.migrate()
        self.assertEqual(self.store.integrity_problems(), [])
        names = {r[0] for r in self.store.conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        self.assertTrue({"events_no_update", "events_no_delete"} <= names)


if __name__ == "__main__":
    unittest.main()
