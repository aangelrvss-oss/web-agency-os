"""Approvals bound to the SHA-256 of the canonical JSON of the exact action (data-contracts § 8).

M1 action kinds: SHORTLIST {kind, lead_id, score_id} and BUDGET_CHANGE {kind, global_cap_cents, per_run_cap_cents}.
Operator identity is self-declared on the CLI (architecture § 6.3): approvals are attributable, not authenticated.
"""
import datetime as dt
import json
import os

from . import schema
from .util import CONFIG, iso, load_json, new_id, parse_iso, sha256_obj

M1_TYPES = ("SHORTLIST", "BUDGET_CHANGE")


class ApprovalError(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def action_hash(action):
    return sha256_obj(action)


def _save(store, doc):
    schema.validate("approval", doc)
    store.conn.execute("INSERT INTO approvals(approval_id, type, action_sha256, status, execution_count, doc) "
                       "VALUES (?,?,?,?,?,?) ON CONFLICT(approval_id) DO UPDATE SET status=excluded.status, "
                       "execution_count=excluded.execution_count, doc=excluded.doc",
                       (doc["approval_id"], doc["type"], doc["action_sha256"], doc["status"], doc["execution_count"],
                        json.dumps(doc, ensure_ascii=False)))


def get(store, approval_id):
    return store.doc("approvals", "approval_id", approval_id)


def request(store, type_, action, actor):
    if type_ not in M1_TYPES:
        raise ApprovalError("TYPE_HAS_NO_EXECUTOR_IN_M1")
    if action.get("kind") != type_:
        raise ApprovalError("TYPE_MISMATCH")
    hours = load_json(os.path.join(CONFIG, "waos.config.json"))["approval_expiry_hours"][type_]
    now = store.clock()
    doc = {"schema_version": "waos.approval.v1", "approval_id": new_id("apr_"), "type": type_, "action": action,
           "action_sha256": action_hash(action), "requested_by": actor, "requested_at": iso(now),
           "expires_at": iso(now + dt.timedelta(hours=hours)), "decision": None, "status": "PENDING",
           "executed_at": None, "execution_count": 0}
    with store.tx():
        _save(store, doc)
        store.event("approval.requested", actor, action.get("lead_id"),
                    {"approval_id": doc["approval_id"], "type": type_, "action_sha256": doc["action_sha256"]},
                    refs=[doc["approval_id"]])
    return doc


def _reject(store, approval_id, actor, reason, lead_id=None):
    store.event("approval.rejected", actor, lead_id, {"approval_id": approval_id, "reason": reason},
                refs=[approval_id] if approval_id else [])
    raise ApprovalError(reason)


def _update_if(store, doc, expected_status):
    """Conditional write: succeeds only if the stored row is still in `expected_status` and never executed."""
    schema.validate("approval", doc)
    cur = store.conn.execute("UPDATE approvals SET status=?, execution_count=?, doc=? WHERE approval_id=? AND status=? "
                             "AND execution_count=0",
                             (doc["status"], doc["execution_count"], json.dumps(doc, ensure_ascii=False),
                              doc["approval_id"], expected_status))
    return cur.rowcount == 1


def decide(store, approval_id, decision, actor, comment=None):
    """Read, validate and write inside one write transaction; a stale read cannot overwrite a decision."""
    reason, lead_id = None, None
    with store.tx():
        doc = get(store, approval_id)
        if doc is None:
            reason = "NOT_FOUND"
        else:
            lead_id = doc["action"].get("lead_id")
            if not actor.startswith("human:"):
                reason = "DECIDER_NOT_HUMAN"
            elif decision not in ("APPROVED", "REJECTED"):
                reason = "INVALID_DECISION"
            elif doc["status"] != "PENDING":
                reason = f"NOT_PENDING:{doc['status']}"
            elif store.clock() > parse_iso(doc["expires_at"]):
                reason = "EXPIRED"
                _update_if(store, dict(doc, status="EXPIRED"), "PENDING")
            else:
                doc = dict(doc, status=decision,
                           decision={"decision": decision, "by": actor, "at": store.now(), "comment": comment})
                if _update_if(store, doc, "PENDING"):
                    store.event("approval.decided", actor, lead_id, {"approval_id": approval_id, "decision": decision},
                                refs=[approval_id])
                else:
                    reason = "NOT_PENDING:CHANGED"
    if reason:
        _reject(store, approval_id, actor if reason != "NOT_FOUND" else "system", reason, lead_id)
    return doc


def check(store, approval_id, action, expected_type):
    """Return the reason this approval cannot authorize `action`, or None if it can."""
    doc = get(store, approval_id)
    if doc is None:
        return "NOT_FOUND"
    if doc["type"] != expected_type or action.get("kind") != expected_type:
        return "TYPE_MISMATCH"
    if doc["execution_count"] or doc["status"] == "EXECUTED":
        return "ALREADY_EXECUTED"
    if doc["status"] != "APPROVED":
        return f"NOT_APPROVED:{doc['status']}"
    if not (doc["decision"] or {}).get("by", "").startswith("human:"):
        return "DECIDER_NOT_HUMAN"
    if store.clock() > parse_iso(doc["expires_at"]):
        return "EXPIRED"
    if action_hash(action) != doc["action_sha256"]:
        return "HASH_MISMATCH"
    return None


def consume(store, approval_id, action, expected_type, actor):
    """Re-check and mark as executed. Call INSIDE the same write transaction as the authorized effect: the check and
    the conditional update are atomic, so an approval executes at most once even after a stale pre-check."""
    reason = check(store, approval_id, action, expected_type)
    if reason:
        raise ApprovalError(reason)
    doc = dict(get(store, approval_id), status="EXECUTED", execution_count=1, executed_at=store.now())
    if not _update_if(store, doc, "APPROVED"):
        raise ApprovalError("ALREADY_EXECUTED")
    store.event("approval.executed", actor, doc["action"].get("lead_id"),
                {"approval_id": approval_id, "type": doc["type"], "action_sha256": doc["action_sha256"]},
                refs=[approval_id])


def reject(store, approval_id, actor, reason, lead_id=None):
    _reject(store, approval_id, actor, reason, lead_id)
