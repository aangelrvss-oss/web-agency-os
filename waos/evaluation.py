"""Evaluation status of a lead's diagnosis (M2a.1), derived only from stored evidence and findings.

PROBLEMS_FOUND         at least one finding is KNOWN and every evidence record it cites is stored, KNOWN and not erased.
NO_PROBLEMS_FOUND      no confirmed problem, and every check in the declared scope has KNOWN evidence NOT_DETECTED.
INSUFFICIENT_EVIDENCE  anything else: an in-scope check is UNKNOWN, missing or contradictory.

The scope (rules/diagnosis.v1.json `evaluation_scope`) is the set of checks whose absence the procedure can establish.
NO_PROBLEMS_FOUND says nothing about the other checks: they are always listed as not verified. The status is separate
from the review bucket: a LOW bucket is not a healthy site.
"""
from . import evidence as E
from .diagnose import CHECKS, rules

STATUSES = ("PROBLEMS_FOUND", "NO_PROBLEMS_FOUND", "INSUFFICIENT_EVIDENCE")
CHECK_PREFIX = "site.check."


def evaluate(evidence, findings, cfg=None):
    cfg = cfg or rules()
    ev = {e["evidence_id"]: e for e in evidence if not e["erased"]}

    def valid(f):
        return (f["claim_status"] == "KNOWN" and bool(f["evidence_ids"])
                and all(i in ev and ev[i]["claim_status"] == "KNOWN" for i in f["evidence_ids"]))

    confirmed = sorted({f["code"] for f in findings if valid(f)})
    clear, pending, procedures = [], [], set()
    for code in CHECKS:
        rows = [e for e in ev.values() if e["field"] == CHECK_PREFIX + code]
        procedures |= {e["method"]["tool_version"] for e in rows}
        status, value, _ = E.resolve(rows, CHECK_PREFIX + code)      # two different KNOWN values → CONFLICTING
        if code in confirmed:
            continue
        if status == "KNOWN" and value == "NOT_DETECTED":
            clear.append(code)
            continue
        reasons = sorted({e["method"]["procedure_id"] for e in rows if e["claim_status"] != "KNOWN"})
        reason = ("CONFLICTING_EVIDENCE" if status == "CONFLICTING" else
                  "DETECTED_WITHOUT_VALID_FINDING" if status == "KNOWN" else
                  reasons[0] if reasons else "NO_EVIDENCE")
        pending.append({"code": code, "in_scope": code in cfg["evaluation_scope"], "reason_code": reason})
    if confirmed:
        status = "PROBLEMS_FOUND"
    elif all(code in clear for code in cfg["evaluation_scope"]):
        status = "NO_PROBLEMS_FOUND"
    else:
        status = "INSUFFICIENT_EVIDENCE"
    return {"status": status, "procedure": ";".join(sorted(procedures)) or None, "scope": list(cfg["evaluation_scope"]),
            "confirmed": confirmed, "clear": clear, "pending": pending}


def evaluate_lead(store, lead_id, cfg=None):
    return evaluate(store.evidence_for(lead_id), store.findings_for(lead_id), cfg)
