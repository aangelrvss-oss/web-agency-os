"""Suppression, erasure and retention (data-contracts § 10). Events carry ids and counts only (D-024)."""
import json
import os
import re

import datetime as dt

from . import evidence as E
from . import schema, workflow
from .util import CONFIG, iso, load_json, new_id, sha256_text

LEAD_PERSONAL_FIELDS = ("phone", "email", "owner_name")


def _salt():
    return load_json(os.path.join(CONFIG, "waos.config.json"))["suppression_salt"]


def normalized_identifiers(lead, evidence):
    out = set()
    domain = (lead["business"].get("domain") or "").lower().removeprefix("www.")
    if domain:
        out.add(f"domain:{domain}")
    phones = [lead["business"].get("phone")] + [e["value"] for e in evidence
                                                 if e["field"] == "business.phone" and not e["erased"]]
    emails = [lead["business"].get("email")] + [e["value"] for e in evidence
                                                 if e["field"] == "business.email" and not e["erased"]]
    out |= {f"phone:{re.sub(r'[^0-9]', '', p)}" for p in phones if p}
    out |= {f"email:{m.strip().lower()}" for m in emails if m}
    return out


def identifier_hashes(lead, evidence):
    salt = _salt()
    return sorted(sha256_text(salt + ident) for ident in normalized_identifiers(lead, evidence))


def is_suppressed(store, hashes):
    if not hashes:
        return False
    q = ",".join("?" * len(hashes))
    return store.conn.execute(f"SELECT 1 FROM suppression_hashes WHERE hash IN ({q})", list(hashes)).fetchone() is not None


def _erase_rows(store, lead_id, rows):
    """Null personal values and snippets; make the underlying captures unavailable (E6). Inside a transaction."""
    shas = {e["capture_sha256"] for e in rows if e.get("capture_sha256")}
    for e in rows:
        e.update(value=None, snippet=None, erased=True, capture_available=False)
        store.put_evidence(e, insert=False)
    for sha in shas:
        store.conn.execute("UPDATE captures SET text=NULL, available=0 WHERE capture_sha256=?", (sha,))
        for other in store.docs("evidence", "json_extract(doc, '$.capture_sha256') = ?", (sha,)):
            if other["capture_available"]:
                other["capture_available"] = False
                store.put_evidence(other, insert=False)
    lead = store.lead(lead_id)
    cleared = [f for f in LEAD_PERSONAL_FIELDS if lead["business"].get(f) is not None]
    for f in cleared:
        lead["business"][f] = None
    if cleared:
        store.put_lead(lead, last_transition_at=store.last_transition_at(lead_id))
    return cleared


def erase(store, lead_id, actor):
    rows = [e for e in store.evidence_for(lead_id) if e["personal_data"] != "NONE" and not e["erased"]]
    with store.tx():
        cleared = _erase_rows(store, lead_id, rows)
        store.event("evidence.erased", actor, lead_id,
                    {"evidence_ids": [e["evidence_id"] for e in rows], "lead_fields_cleared": cleared},
                    refs=[e["evidence_id"] for e in rows])
    return [e["evidence_id"] for e in rows]


def suppress(store, lead_id, reason, actor, source_ref=None):
    lead = store.lead(lead_id)
    hashes = identifier_hashes(lead, store.evidence_for(lead_id))
    doc = {"schema_version": "waos.suppression.v1", "suppression_id": new_id("sup_"), "identifiers_sha256": hashes,
           "reason": reason, "created_at": store.now(), "source_ref": source_ref}
    schema.validate("suppression", doc)
    with store.tx():
        store.conn.execute("INSERT INTO suppressions(suppression_id, reason, doc) VALUES (?,?,?)",
                           (doc["suppression_id"], reason, json.dumps(doc)))
        store.conn.executemany("INSERT OR IGNORE INTO suppression_hashes(hash, suppression_id) VALUES (?,?)",
                               [(h, doc["suppression_id"]) for h in hashes])
        store.event("suppression.recorded", actor, lead_id,
                    {"suppression_id": doc["suppression_id"], "reason": reason, "hash_count": len(hashes)},
                    refs=[doc["suppression_id"]])
    erase(store, lead_id, actor)
    lead = store.lead(lead_id)
    if lead["state"] in workflow.table()[1]:            # terminal: keep state, mark suppressed
        lead["suppressed"] = True
        with store.tx():
            store.put_lead(lead, last_transition_at=store.last_transition_at(lead_id))
    else:
        workflow.transition(store, lead_id, "SUPPRESSED", actor, _suppression=True)
    return doc


def retention_run(store, actor):
    today = store.clock().strftime("%Y-%m-%d")
    rows = store.docs("evidence", "erased = 0 AND personal_data <> 'NONE' AND retention_until < ?", (today,))
    by_lead = {}
    for e in rows:
        by_lead.setdefault(e["subject"]["lead_id"], []).append(e)
    cutoff = iso(store.clock() - dt.timedelta(days=E.retention_days()["BUSINESS_CONTACT"]))
    stale_leads = [lead["lead_id"] for lead in store.docs("leads")
                   if lead["created_at"] < cutoff and any(lead["business"].get(f) for f in LEAD_PERSONAL_FIELDS)]
    with store.tx():
        for lead_id, lead_rows in by_lead.items():
            _erase_rows(store, lead_id, lead_rows)
        for lead_id in stale_leads:                      # contact fields held on the lead without evidence rows
            _erase_rows(store, lead_id, [])
        store.event("retention.purged", actor, None,
                    {"count": len(rows), "evidence_ids": sorted(e["evidence_id"] for e in rows),
                     "lead_ids_cleared": sorted(set(stale_leads) | set(by_lead))},
                    refs=sorted(e["evidence_id"] for e in rows))
    return [e["evidence_id"] for e in rows]


def event_leaks(store, values):
    """Personal values found in any stored event document (should always be empty)."""
    docs = [r["doc"] for r in store.conn.execute("SELECT doc FROM events")]
    return sorted({v for v in values if v and any(v in d for d in docs)})
