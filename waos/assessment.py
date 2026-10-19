"""Three-layer assessment (data-contracts § 6): technical evidence → acquisition impact → commercial opportunity.

The bucket is a priority for human review. It is never a probability, and nothing here touches purchase_intent.
"""
import json
import os

from . import evidence as E
from . import schema
from .util import RULES, load_json, new_id, parse_date, sha256_obj

RULE_FILES = ("scoring.v1.json", "impact_rules.v1.json", "evidence_strength.v1.json")


def load_rules():
    return {name: load_json(os.path.join(RULES, name)) for name in RULE_FILES}


def rules_hash(rules):
    return sha256_obj(rules)


def _gate(gate_id, result, ids=()):
    return {"gate_id": gate_id, "result": result, "evidence_ids": list(ids)}


def _gates(lead, campaign, ev, cfg, now):
    gates = []
    st = lead["identity"]["status"]
    gates.append(_gate("G_IDENTITY", {"KNOWN_MATCH": "PASS", "KNOWN_MISMATCH": "FAIL"}.get(st, "UNKNOWN"),
                       lead["identity"]["evidence_ids"]))

    g = cfg["G_GEO"]
    status, value, ids = E.resolve(ev, g["fields"][0], g["acceptable_sources"])
    area = set(campaign["area"]["municipalities"])
    gates.append(_gate("G_GEO", ("PASS" if value in area else "FAIL") if status == "KNOWN" else "UNKNOWN", ids))

    g = cfg["G_CATEGORY"]
    status, category, ids = E.resolve(ev, g["fields"][0], g["acceptable_sources"])
    cats = set(campaign["categories"])
    gates.append(_gate("G_CATEGORY", ("PASS" if category in cats else "FAIL") if status == "KNOWN" else "UNKNOWN", ids))

    g = cfg["G_ACTIVE"]
    closed_status, closed, closed_ids = E.resolve(ev, g["status_field"], g["acceptable_sources"])
    status, dated, ids = E.resolve(ev, g["fields"][0], g["acceptable_sources"])
    if closed_status == "KNOWN" and closed == "CLOSED":
        gates.append(_gate("G_ACTIVE", "FAIL", closed_ids))
    elif status == "KNOWN" and 0 <= (now - parse_date(dated)).days <= g["window_days"]:
        gates.append(_gate("G_ACTIVE", "PASS", ids))
    else:
        gates.append(_gate("G_ACTIVE", "UNKNOWN", ids))      # an old or future date proves nothing

    excluded = (lead["suppressed"] or lead["entity_key"] in campaign.get("existing_client_keys", [])
                or lead["entity_key"] in campaign.get("competitor_keys", []))
    gates.append(_gate("G_NOT_EXCLUDED", "FAIL" if excluded else "PASS"))
    return gates


def _tg(findings, levels):
    def level(fs):
        sev = [f["technical_severity"] for f in fs]
        if "CRITICAL" in sev or sev.count("MAJOR") >= 2:
            return levels["critical_or_two_major"]
        if "MAJOR" in sev:
            return levels["major"]
        if "MINOR" in sev:
            return levels["minor"]
        return 0
    known = [f for f in findings if f["claim_status"] == "KNOWN"]
    possible = [f for f in findings if f["claim_status"] in ("KNOWN", "INFERRED")]
    return {"floor": level(known), "ceiling": max(level(known), level(possible)),
            "finding_ids": [f["finding_id"] for f in possible]}


def _im(findings, impact_rules):
    lv = impact_rules["levels"]

    def level(fs):
        return max([lv[impact_rules["impact"][f["code"]]] for f in fs if f["code"] in impact_rules["impact"]] or [0])
    known = [f for f in findings if f["claim_status"] == "KNOWN"]
    possible = [f for f in findings if f["claim_status"] in ("KNOWN", "INFERRED")]
    used = sorted({f["code"] for f in possible if f["code"] in impact_rules["impact"]})
    return {"floor": level(known), "ceiling": max(level(known), level(possible)), "impact_rule_ids": used}


def _prefixed(ev, prefix):
    rows = [e for e in ev if e["field"].startswith(prefix) and not e["erased"] and e["value"] is not False]
    by_code = {}
    for e in rows:
        by_code.setdefault(e["field"][len(prefix):], []).append(e)
    return by_code


def _confidence(gates, ev_by_id, im_known):
    if any(g["result"] != "PASS" for g in gates):
        return "NONE"
    strengths = [ev_by_id[i]["strength"] for g in gates for i in g["evidence_ids"] if i in ev_by_id]
    if "LOW" in strengths:
        return "LOW_ONLY"
    if strengths and all(s == "HIGH" for s in strengths) and im_known:
        return "STRONG"
    if "MEDIUM" in strengths or "HIGH" in strengths:
        return "MODERATE"
    return "NONE"


def assess(lead, campaign, evidence, findings, now, rules=None):
    """Pure function: same inputs and rules ⇒ same record (except score_id / computed_at)."""
    rules = rules or load_rules()
    sc, impact = rules["scoring.v1.json"], rules["impact_rules.v1.json"]
    ev = [e for e in evidence if not e["erased"]]
    ev_by_id = {e["evidence_id"]: e for e in ev}
    gates = _gates(lead, campaign, ev, sc["gates"], now)
    explanation = [f"{g['gate_id']}={g['result']}" for g in gates]

    tg = _tg(findings, sc["tg_levels"])
    im = _im(findings, impact)

    bands, levels = campaign.get("category_value_bands", {}), sc["band_levels"]
    cat_status, category, cat_ids = E.resolve(ev, sc["gates"]["G_CATEGORY"]["fields"][0],
                                              sc["gates"]["G_CATEGORY"]["acceptable_sources"])
    band = bands.get(category, "UNKNOWN") if cat_status == "KNOWN" else "UNKNOWN"
    bv = ({"floor": levels[band], "ceiling": levels[band]} if band in levels else {"floor": 0, "ceiling": 3})
    bv["evidence_ids"] = cat_ids
    explanation.append(f"BV band={band}")

    signals = _prefixed(ev, sc["activity_signal_prefix"])
    known_sig = [c for c, rows in signals.items() if any(r["claim_status"] == "KNOWN" for r in rows)]
    open_sig = [c for c, rows in signals.items() if c not in known_sig]
    ac = {"floor": min(3, len(known_sig)), "ceiling": min(3, len(known_sig) + len(open_sig)),
          "evidence_ids": sorted(r["evidence_id"] for rows in signals.values() for r in rows)}

    cx = []
    for code, rows in sorted(_prefixed(ev, sc["contraindication_prefix"]).items()):
        st, _, ids = E.resolve(rows, rows[0]["field"])
        cx.append({"code": code, "claim_status": st, "evidence_ids": ids})
    cx_known = any(c["claim_status"] == "KNOWN" for c in cx)

    im_known = any(f["claim_status"] == "KNOWN" for f in findings if f["code"] in impact["impact"])
    confidence = _confidence(gates, ev_by_id, im_known)

    b = sc["buckets"]
    rp, w = b["REVIEW_PRIORITY"], b["WATCH"]
    if any(g["result"] == "FAIL" for g in gates):
        bucket = "DISQUALIFIED"
    elif any(g["result"] == "UNKNOWN" for g in gates):
        bucket = "PENDING"
    elif (im["floor"] >= rp["IM_floor_min"] and bv["floor"] >= rp["BV_floor_min"] and ac["floor"] >= rp["AC_floor_min"]
          and not cx_known and confidence in rp["confidence"]):
        bucket = "REVIEW_PRIORITY"
    elif im["floor"] >= w["IM_floor_min"] or tg["floor"] >= w["TG_floor_min"]:
        bucket = "WATCH"
    else:
        bucket = "LOW"
    if cx_known:
        explanation.append("contraindication KNOWN: capped below REVIEW_PRIORITY")
    explanation.append(f"bucket={bucket}")

    record = {
        "schema_version": "waos.score.v1", "score_id": new_id("scr_"), "lead_id": lead["lead_id"],
        "scoring_version": sc["scoring_version"], "rules_hash": rules_hash(rules),
        "computed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "gates": gates,
        "layer1": {"TG": tg}, "layer2": {"IM": im},
        "layer3": {"BV": bv, "AC": ac, "contraindications": cx,
                   "opportunity_points": {"floor": im["floor"] + bv["floor"] + ac["floor"],
                                          "ceiling": im["ceiling"] + bv["ceiling"] + ac["ceiling"]},
                   "confidence_band": confidence, "bucket": bucket},
        "explanation": explanation, "calibrated": False, "disclaimer": sc["disclaimer"]}
    return schema.validate("score", record)


def score_lead(store, lead_id, actor="system", rules=None):
    lead = store.lead(lead_id)
    record = assess(lead, store.campaign(lead["campaign_id"]), store.evidence_for(lead_id),
                    store.findings_for(lead_id), store.clock(), rules)
    with store.tx():
        store.conn.execute("INSERT INTO scores(score_id, lead_id, rules_hash, bucket, computed_at, doc) VALUES (?,?,?,?,?,?)",
                           (record["score_id"], lead_id, record["rules_hash"], record["layer3"]["bucket"],
                            record["computed_at"], json.dumps(record, ensure_ascii=False)))
        store.event("score.computed", actor, lead_id,
                    {"score_id": record["score_id"], "rules_hash": record["rules_hash"],
                     "bucket": record["layer3"]["bucket"]}, refs=[record["score_id"]])
    return record
