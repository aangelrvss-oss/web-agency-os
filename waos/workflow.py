"""Lead state machine (architecture § 5.4, rules/transitions.v1.json). Every pair not in the table is rejected."""
import os

from . import approvals, assessment
from . import evidence as E
from .store import STATES
from .util import RULES, load_json


class TransitionDenied(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def table():
    t = load_json(os.path.join(RULES, "transitions.v1.json"))
    terminal = set(t["terminal"])
    rules = {}
    for r in t["transitions"]:
        sources = [s for s in STATES if s not in terminal and s != r["to"]] if r["from"] == "ANY_NON_TERMINAL" \
            else [r["from"]]
        for s in sources:
            rules.setdefault((s, r["to"]), r["guard"])
    return rules, terminal


def _current_score(store, lead_id):
    score = store.latest_score(lead_id)
    if score and score["rules_hash"] == assessment.rules_hash(assessment.load_rules()):
        return score
    return None


def _duplicate(store, lead):
    row = store.conn.execute("SELECT lead_id FROM leads WHERE entity_key=? AND lead_id<>? AND rowid < "
                             "(SELECT rowid FROM leads WHERE lead_id=?)",
                             (lead["entity_key"], lead["lead_id"], lead["lead_id"])).fetchone()
    return row is not None or bool(lead["identity"].get("duplicate_of"))


def _human_identity(store, lead, wanted):
    rows = [e for e in store.evidence_for(lead["lead_id"]) if e["source_class"] == "HUMAN_REVIEW"]
    status, value, ids = E.resolve(rows, "identity.resolution")
    if status == "KNOWN" and value == wanted:
        lead["identity"] = {**lead["identity"], "status": wanted, "evidence_ids": lead["identity"]["evidence_ids"] + ids}
        return True
    return False


def _guard(store, guard, lead, actor, ctx):
    status = lead["identity"]["status"]
    if guard == "identity_known_match":
        return status == "KNOWN_MATCH"
    if guard == "identity_ambiguous_or_unknown":
        return status in ("AMBIGUOUS", "UNKNOWN")
    if guard == "identity_mismatch_or_duplicate":
        return status == "KNOWN_MISMATCH" or _duplicate(store, lead)
    if guard == "human_review_identity_match":
        return _human_identity(store, lead, "KNOWN_MATCH")
    if guard == "human_review_identity_mismatch":
        return _human_identity(store, lead, "KNOWN_MISMATCH")
    if guard == "diagnosis_recorded":
        return lead["diagnosis_recorded"]
    if guard == "human_decision":
        return actor.startswith("human:")
    if guard == "suppression_request":
        return ctx.get("suppression") is True
    score = _current_score(store, lead["lead_id"])
    bucket = score["layer3"]["bucket"] if score else None
    if guard == "current_score_exists":
        return score is not None
    if guard == "bucket_watch_low_or_pending":
        return bucket in ("WATCH", "LOW", "PENDING")
    if guard == "bucket_disqualified":
        return bucket == "DISQUALIFIED"
    if guard == "new_score_after_parking":
        return score is not None and score["computed_at"] > store.last_transition_at(lead["lead_id"])
    if guard == "review_priority_and_shortlist_approval":
        if bucket != "REVIEW_PRIORITY":
            return False
        approval_id = ctx.get("approval_id")
        if not approval_id:
            raise TransitionDenied("APPROVAL_REQUIRED")
        action = {"kind": "SHORTLIST", "lead_id": lead["lead_id"], "score_id": score["score_id"]}
        reason = approvals.check(store, approval_id, action, "SHORTLIST")
        if reason:
            raise TransitionDenied(f"APPROVAL:{reason}")
        ctx["consume_approval"] = (approval_id, action)
        return True
    raise ValueError(f"unknown guard {guard}")


def transition(store, lead_id, to, actor, expected_version=None, approval_id=None, _suppression=False):
    """Apply one transition, or record `state.transition_denied` and raise TransitionDenied."""
    ctx = {"approval_id": approval_id, "suppression": _suppression}
    lead = store.lead(lead_id)
    original_state = lead["state"] if lead else None
    try:
        if lead is None:
            raise TransitionDenied("LEAD_NOT_FOUND")
        rules, terminal = table()
        frm = lead["state"]
        if to not in STATES:
            raise TransitionDenied("UNKNOWN_STATE")
        if frm in terminal:
            raise TransitionDenied("TERMINAL_STATE")
        if expected_version is not None and expected_version != lead["state_version"]:
            raise TransitionDenied("STALE_VERSION")
        key = (frm, "PREVIOUS_STATE") if frm == "ON_HOLD" and to == lead["on_hold_from"] else (frm, to)
        guard = rules.get(key)
        if guard is None:
            raise TransitionDenied("NOT_ALLOWED")
        if not _guard(store, guard, lead, actor, ctx):
            raise TransitionDenied(f"GUARD_FAILED:{guard}")
        version = lead["state_version"]
        lead["on_hold_from"] = frm if to == "ON_HOLD" else (None if frm == "ON_HOLD" else lead["on_hold_from"])
        lead["state"], lead["state_version"] = to, version + 1
        if to == "SUPPRESSED":
            lead["suppressed"] = True
        with store.tx():
            cur = store.conn.execute("SELECT state_version FROM leads WHERE lead_id=?", (lead_id,)).fetchone()
            if cur[0] != version:
                raise TransitionDenied("STALE_VERSION")
            if ctx.get("consume_approval"):
                try:
                    approvals.consume(store, *ctx["consume_approval"], "SHORTLIST", actor)
                except approvals.ApprovalError as e:
                    raise TransitionDenied(f"APPROVAL:{e.reason}")
            store.put_lead(lead)
            store.event("state.transitioned", actor, lead_id,
                        {"from": frm, "to": to, "guard": guard, "state_version": lead["state_version"]},
                        refs=[approval_id] if approval_id else [])
        return lead
    except TransitionDenied as denied:
        store.event("state.transition_denied", actor, lead_id if lead else None,
                    {"from": original_state, "to": to, "reason": denied.reason},
                    refs=[approval_id] if approval_id else [])
        raise
