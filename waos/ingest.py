"""Import of synthetic fixtures. M1 accepts data_mode SYNTHETIC or TEST_FIXTURE only; REAL is rejected."""
import json

from . import evidence as E
from . import privacy, schema
from .util import sha256_text

ALLOWED_MODES = ("SYNTHETIC", "TEST_FIXTURE")


class ImportRejected(Exception):
    pass


def _modes(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "data_mode":
                yield v
            yield from _modes(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _modes(v)


def import_fixture(store, fixture, actor="system"):
    bad = [m for m in _modes(fixture) if m not in ALLOWED_MODES]
    if bad or fixture.get("data_mode") not in ALLOWED_MODES:
        store.event("import.rejected", actor, None, {"reason": "DATA_MODE_NOT_ALLOWED_IN_M1"})
        raise ImportRejected("DATA_MODE_NOT_ALLOWED_IN_M1")
    mode = fixture["data_mode"]
    now = store.now()
    camp = fixture["campaign"]
    captures = {ref: sha256_text(text) for ref, text in fixture.get("captures", {}).items()}
    with store.tx():
        store.conn.execute("INSERT OR IGNORE INTO campaigns(campaign_id, data_mode, doc) VALUES (?,?,?)",
                           (camp["campaign_id"], camp["data_mode"], json.dumps(camp, ensure_ascii=False)))
        for ref, text in fixture.get("captures", {}).items():
            store.conn.execute("INSERT OR IGNORE INTO captures(capture_sha256, text, available) VALUES (?,?,1)",
                               (captures[ref], text))
    summary = {"leads_imported": 0, "leads_rejected": 0, "evidence_recorded": 0, "evidence_rejected": 0,
               "findings_recorded": 0}
    for entry in fixture["leads"]:
        src = entry["lead"]
        lead = {"schema_version": "waos.lead.v1", "lead_id": src["lead_id"], "campaign_id": camp["campaign_id"],
                "entity_key": src["entity_key"], "state": "DISCOVERED", "state_version": 0,
                "business": src["business"], "identity": src["identity"], "purchase_intent": "UNKNOWN",
                "suppressed": False, "on_hold_from": None, "diagnosis_recorded": "findings" in entry,
                "data_mode": mode, "created_at": now}
        errors = schema.errors_for(schema.contract("lead"), lead)
        reason = ("SCHEMA_INVALID" if errors else
                  "DUPLICATE_LEAD_ID" if store.lead(lead["lead_id"]) else
                  "SUPPRESSED_IDENTIFIER" if privacy.is_suppressed(store, privacy.identifier_hashes(lead, [])) else None)
        if reason:
            store.event("import.rejected", actor, None,
                        {"lead_id": lead["lead_id"], "reason": reason, "errors": [e.split(":")[0] for e in errors]})
            summary["leads_rejected"] += 1
            continue
        with store.tx():
            store.put_lead(lead, last_transition_at=now, insert=True)
            store.event("import.completed", actor, lead["lead_id"], {"lead_id": lead["lead_id"], "stage": "lead"})
        summary["leads_imported"] += 1
        for ev in entry.get("evidence", []):
            ev = dict(ev)
            ref = ev.pop("capture_ref", None)
            if ref:
                ev["capture_sha256"] = captures[ref]
            full = {"schema_version": "waos.evidence.v1",
                    "subject": {"lead_id": lead["lead_id"], "entity_key": lead["entity_key"]},
                    "evidence_origin": "FIXTURE", "method": {"tool": "fixture", "tool_version": "m1",
                                                             "procedure_id": "FIXTURE"},
                    "retrieved_at": now, "confidence": "HIGH", "proposed_by": "fixture", "personal_data": "NONE",
                    "source_url": None, "snippet": None, "data_mode": mode, **ev}
            ok = E.record(store, full, actor)
            summary["evidence_recorded" if ok else "evidence_rejected"] += 1
        for f in entry.get("findings", []):
            doc = {"schema_version": "waos.finding.v1", "lead_id": lead["lead_id"], "measured_value": None,
                   "threshold_param": None, "rule_version": "catalogue.v1", "evidence_ids": [], "sales_safe": True,
                   "detected_at": now, "data_mode": mode, **f}
            schema.validate("finding", doc)
            with store.tx():
                store.conn.execute("INSERT INTO findings(finding_id, lead_id, code, technical_severity, claim_status, doc)"
                                   " VALUES (?,?,?,?,?,?)", (doc["finding_id"], lead["lead_id"], doc["code"],
                                                             doc["technical_severity"], doc["claim_status"],
                                                             json.dumps(doc, ensure_ascii=False)))
                store.event("finding.recorded", actor, lead["lead_id"],
                            {"finding_id": doc["finding_id"], "code": doc["code"],
                             "technical_severity": doc["technical_severity"], "claim_status": doc["claim_status"]},
                            refs=[doc["finding_id"]])
            summary["findings_recorded"] += 1
    store.event("import.completed", actor, None, {"stage": "fixture", **summary})
    return summary
