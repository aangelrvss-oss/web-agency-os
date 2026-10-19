"""Evidence invariants (data-contracts § 3), derived strength, and field resolution (KNOWN / CONFLICTING / …)."""
import datetime as dt
import os

from . import schema
from .util import CONFIG, RULES, load_json, parse_date

TEXTUAL_SOURCES = {"OFFICIAL", "PUBLIC_REGISTRY", "PROFESSIONAL_DIRECTORY", "SECTOR_SOURCE", "OTHER_VERIFIABLE"}
CONTACT_FIELDS = {"business.phone", "business.email"}
DATE_FIELDS = {"business.activity_dated"}
PERSONAL_FIELDS = CONTACT_FIELDS | {"business.owner_name"}


def strength_rules():
    return load_json(os.path.join(RULES, "evidence_strength.v1.json"))


def retention_days():
    return load_json(os.path.join(CONFIG, "retention.v1.json"))["days"]


def strength(ev, now, rules=None):
    rules = rules or strength_rules()
    dated = ev.get("dated_on")
    facts = {"claim_status": ev["claim_status"], "source_class": ev["source_class"],
             "corroborated": bool(ev.get("corroborated")),
             "dated_within_freshness": bool(dated) and (now - parse_date(dated)).days
             <= rules["freshness_days_for_dated_sector_source"]}
    for rule in rules["rules"]:
        if all(facts.get(k) in allowed for k, allowed in rule["when"].items()):
            return rule["strength"]
    return rules["default"]


def problems(ev, capture_text):
    """Invariant violations beyond the JSON Schema. capture_text(sha) -> text or None."""
    out = []
    known = ev["claim_status"] == "KNOWN"
    if ev["field"] in PERSONAL_FIELDS and ev["personal_data"] == "NONE":
        out.append("PERSONAL_DATA_UNMARKED")
    if ev["field"] in DATE_FIELDS and ev["value"] is not None:
        try:
            parse_date(str(ev["value"]))
        except ValueError:
            out.append("INVALID_DATE_VALUE")
    if not known:
        return out
    if ev.get("seen_in") == "SEARCH_SNIPPET":
        out.append("SEARCH_SNIPPET_NOT_KNOWN")
    if ev.get("kind") == "INFERENCE":
        out.append("INFERENCE_NOT_KNOWN")
    snippet = ev.get("snippet")
    if ev["source_class"] in TEXTUAL_SOURCES:
        if not (snippet or "").strip():
            out.append("SNIPPET_REQUIRED")
        elif not ev.get("capture_sha256"):
            out.append("CAPTURE_REQUIRED")
        else:
            text = capture_text(ev["capture_sha256"])
            if text is None:
                out.append("CAPTURE_UNAVAILABLE")
            elif snippet not in text:
                out.append("SNIPPET_NOT_IN_CAPTURE")
    if ev["field"] in CONTACT_FIELDS:
        value = str(ev["value"])
        hay = (snippet or "")
        if ev["field"] == "business.email":
            value, hay = value.lower(), hay.lower()
        if not (snippet or "").strip() or value not in hay:
            out.append("CONTACT_NOT_LITERAL")
    return out


def record(store, ev, actor="system"):
    """Validate and store one evidence record. Returns True if stored. Rejections are events without values."""
    now = store.clock()
    ev = dict(ev)
    ev.setdefault("erased", False)
    ev.setdefault("capture_available", bool(ev.get("capture_sha256")) and
                  store.capture_text(ev["capture_sha256"]) is not None)
    if ev.get("personal_data", "NONE") != "NONE" and not ev.get("retention_until"):
        days = retention_days()[ev["personal_data"]]
        ev["retention_until"] = (now + dt.timedelta(days=days)).strftime("%Y-%m-%d")
    reasons = [f"SCHEMA:{e.split(':')[0]}" for e in schema.errors_for(schema.contract("evidence"), ev)]
    lead_id = (ev.get("subject") or {}).get("lead_id")
    if not reasons:
        lead = store.lead(lead_id)
        if lead is None:
            reasons = ["LEAD_NOT_FOUND"]
        elif ev["subject"]["entity_key"] != lead["entity_key"]:
            reasons = ["SUBJECT_MISMATCH"]
        elif store.doc("evidence", "evidence_id", ev["evidence_id"]) is not None:
            reasons = ["DUPLICATE_EVIDENCE_ID"]
    if not reasons:
        reasons = problems(ev, store.capture_text)
    if reasons:
        store.event("evidence.rejected", actor, lead_id,
                    {"evidence_id": ev.get("evidence_id"), "field": ev.get("field"), "reasons": reasons})
        return False
    ev["strength"] = strength(ev, now)
    with store.tx():
        store.put_evidence(ev)
        store.event("evidence.recorded", actor, lead_id,
                    {"evidence_id": ev["evidence_id"], "field": ev["field"], "claim_status": ev["claim_status"],
                     "source_class": ev["source_class"], "strength": ev["strength"]}, refs=[ev["evidence_id"]])
    return True


def resolve(evidence, field, sources=None):
    """Resolve a field from evidence: ('KNOWN'|'CONFLICTING'|'INFERRED'|'UNKNOWN', value, evidence_ids).

    Two incompatible KNOWN values give CONFLICTING; neither is chosen (invariant 6)."""
    rows = [e for e in evidence if e["field"] == field and not e["erased"]
            and (sources is None or e["source_class"] in sources)]
    known = [e for e in rows if e["claim_status"] == "KNOWN"]
    values = {str(e["value"]) for e in known}
    if len(values) > 1:
        return "CONFLICTING", None, [e["evidence_id"] for e in known]
    if known:
        return "KNOWN", known[0]["value"], [e["evidence_id"] for e in known]
    inferred = [e for e in rows if e["claim_status"] == "INFERRED"]
    if inferred:
        return "INFERRED", inferred[0]["value"], [e["evidence_id"] for e in inferred]
    return "UNKNOWN", None, []
