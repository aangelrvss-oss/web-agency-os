"""Safe CSV export (data-contracts § 11): formula-injection escaping, full quoting, no values in events."""
import csv
import hashlib
import io
import os

from . import assessment

DANGEROUS_FIRST = ("=", "+", "-", "@", "\t", "\r", "\n", "＝", "＋", "－", "＠")

COLUMNS = ("lead_id", "campaign_id", "business_name", "category", "municipality", "website", "business_phone", "state",
           "priority_for_review", "opportunity_points_floor", "opportunity_points_ceiling", "TG_floor", "IM_floor",
           "BV_floor", "AC_floor", "confidence_band", "contraindications", "unknown_gates", "top_findings",
           "impact_hypotheses", "purchase_intent", "suppressed", "data_mode", "scoring_version", "rules_hash",
           "exported_at")


class ExportRefused(Exception):
    pass


def safe_cell(value):
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(DANGEROUS_FIRST) else text


def _row(store, lead, now):
    score = store.latest_score(lead["lead_id"]) or {}
    l3 = score.get("layer3", {})
    impact = assessment.load_rules()["impact_rules.v1.json"]["impact"]
    codes = sorted({f["code"] for f in store.findings_for(lead["lead_id"])})
    b = lead["business"]
    hide_contact = lead["suppressed"]
    return {
        "lead_id": lead["lead_id"], "campaign_id": lead["campaign_id"], "business_name": b.get("name"),
        "category": b.get("category_id"), "municipality": b.get("municipality"), "website": b.get("website_url"),
        "business_phone": None if hide_contact else b.get("phone"), "state": lead["state"],
        "priority_for_review": l3.get("bucket"),
        "opportunity_points_floor": l3.get("opportunity_points", {}).get("floor"),
        "opportunity_points_ceiling": l3.get("opportunity_points", {}).get("ceiling"),
        "TG_floor": score.get("layer1", {}).get("TG", {}).get("floor"),
        "IM_floor": score.get("layer2", {}).get("IM", {}).get("floor"),
        "BV_floor": l3.get("BV", {}).get("floor"), "AC_floor": l3.get("AC", {}).get("floor"),
        "confidence_band": l3.get("confidence_band"),
        "contraindications": ";".join(f"{c['code']}:{c['claim_status']}" for c in l3.get("contraindications", [])),
        "unknown_gates": ";".join(g["gate_id"] for g in score.get("gates", []) if g["result"] == "UNKNOWN"),
        "top_findings": ";".join(codes),
        "impact_hypotheses": ";".join(f"{c}:{impact[c]}(hypothesis)" for c in codes if c in impact),
        "purchase_intent": lead["purchase_intent"], "suppressed": str(lead["suppressed"]).lower(),
        "data_mode": lead["data_mode"], "scoring_version": score.get("scoring_version"),
        "rules_hash": score.get("rules_hash"), "exported_at": now}


def export_csv(store, out_path, actor="system"):
    leads = store.docs("leads", "1=1 ORDER BY lead_id")
    if any(lead["data_mode"] not in ("SYNTHETIC", "TEST_FIXTURE") for lead in leads):
        store.event("export.refused", actor, None, {"reason": "REAL_DATA_NOT_ALLOWED_IN_M1"})
        raise ExportRefused("REAL_DATA_NOT_ALLOWED_IN_M1")
    now = store.now()
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for lead in leads:
        row = _row(store, lead, now)
        writer.writerow([safe_cell(row[c]) for c in COLUMNS])
    data = buf.getvalue().encode("utf-8")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(data)
    digest = hashlib.sha256(data).hexdigest()
    store.event("export.created", actor, None, {"file_name": os.path.basename(out_path), "sha256": digest,
                                                "row_count": len(leads), "columns": list(COLUMNS)})
    return {"path": out_path, "sha256": digest, "row_count": len(leads)}
