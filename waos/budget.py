"""Spend control + tool gateway (architecture § 9). The gateway is the only way to call a tool.

M1 has FAKE tools only: none of them performs I/O. Paid calls need BOTH the code constant below and the configuration
value to be true (B8); both are false in M1. Unknown price = blocked (B6). Deny, don't truncate (B5).
"""
import json
import os

from . import approvals, schema
from .util import CONFIG, load_json, new_id, sha256_obj

PAID_CALLS_ENABLED = False          # changed only by the user, together with config/waos.config.json

FAKE_TOOLS = {                      # tool -> fn(params) -> (result, actual_cents); no network, no files
    "fake.free_lookup": lambda p: ({"synthetic": True}, 0),
    "fake.priced_lookup": lambda p: ({"synthetic": True}, 5),
    "fake.discounted_lookup": lambda p: ({"synthetic": True}, 4),
    "fake.unpriced_lookup": lambda p: ({"synthetic": True}, 0),
}


def load_config():
    return load_json(os.path.join(CONFIG, "waos.config.json"))


def load_pricing():
    return load_json(os.path.join(CONFIG, "pricing.v1.json"))


def paid_calls_enabled(config=None):
    return bool(PAID_CALLS_ENABLED) and bool((config or load_config())["paid_calls_enabled"])


def caps(store):
    row = store.conn.execute("SELECT global_cap_cents, per_run_cap_cents FROM budget WHERE id=1").fetchone()
    return (row[0], row[1]) if row else None


def spent(store, run_id=None):
    sql, args = "SELECT COALESCE(SUM(actual_cents), 0) FROM ledger WHERE status='OK'", ()
    if run_id:
        sql, args = sql + " AND run_id=?", (run_id,)
    return store.conn.execute(sql, args).fetchone()[0]


def status(store):
    c = caps(store)
    total = spent(store)
    return {"paid_calls_enabled": paid_calls_enabled(), "global_cap_cents": c[0] if c else None,
            "per_run_cap_cents": c[1] if c else None, "spent_cents": total,
            "remaining_cents": (c[0] - total) if c else None}


def _ledger(store, entry):
    schema.validate("ledger_entry", entry)
    store.conn.execute("INSERT INTO ledger(entry_id, run_id, tool, status, actual_cents, doc) VALUES (?,?,?,?,?,?)",
                       (entry["entry_id"], entry["run_id"], entry["tool"], entry["status"], entry["actual_cents"],
                        json.dumps(entry, ensure_ascii=False)))


def call_tool(store, tool, params, run_id, actor="system", config=None, pricing=None):
    """Returns (status, result_or_reason, ledger_entry). Every attempt writes a ledger row and an event."""
    pricing = pricing or load_pricing()
    price = (pricing["tools"].get(tool) or {}).get("unit_price_cents", "missing")
    entry = {"schema_version": "waos.ledger_entry.v1", "entry_id": new_id("led_"), "ts": store.now(), "run_id": run_id,
             "tool": tool, "operation": "invoke", "input_sha256": sha256_obj({"tool": tool, "params": params}),
             "pricing_version": pricing["pricing_version"], "unit_price_cents": price if isinstance(price, int) else None,
             "reserved_cents": 0, "actual_cents": 0, "status": "DENIED", "deny_reason": None,
             "budget_remaining_cents": None}
    with store.tx():
        c = caps(store)
        reason = None
        if tool not in FAKE_TOOLS or price == "missing":
            reason = "TOOL_NOT_ALLOWED"
        elif price is None:
            reason = "UNKNOWN_PRICE"
        elif price > 0:
            if not paid_calls_enabled(config):
                reason = "PAID_CALLS_DISABLED"
            elif c is None:
                reason = "NO_BUDGET"
            elif spent(store) + price > c[0] or spent(store, run_id) + price > c[1]:
                reason = "CAP_EXCEEDED"
        if c:
            entry["budget_remaining_cents"] = c[0] - spent(store)
        if reason:
            entry["deny_reason"] = reason
            _ledger(store, entry)
            store.event("tool.call_denied", actor, None, {"tool": tool, "entry_id": entry["entry_id"], "reason": reason},
                        refs=[entry["entry_id"]], correlation_id=run_id)
            return "DENIED", reason, entry
        result, actual = FAKE_TOOLS[tool](params)
        actual = min(actual, price)                       # settle: never more than the reservation
        entry.update(status="OK", reserved_cents=price, actual_cents=actual)
        if c:
            entry["budget_remaining_cents"] = c[0] - spent(store) - actual
        _ledger(store, entry)
        store.event("tool.call_completed", actor, None,
                    {"tool": tool, "entry_id": entry["entry_id"], "reserved_cents": price, "actual_cents": actual},
                    refs=[entry["entry_id"]], correlation_id=run_id)
        return "OK", result, entry


def change_action(global_cap_cents, per_run_cap_cents):
    return {"kind": "BUDGET_CHANGE", "global_cap_cents": int(global_cap_cents), "per_run_cap_cents": int(per_run_cap_cents)}


def apply_change(store, approval_id, global_cap_cents, per_run_cap_cents, actor):
    """Set caps only through an executed BUDGET_CHANGE approval for exactly these numbers."""
    action = change_action(global_cap_cents, per_run_cap_cents)
    reason = approvals.check(store, approval_id, action, "BUDGET_CHANGE")
    if reason:
        approvals.reject(store, approval_id, actor, reason)
    try:
        with store.tx():
            approvals.consume(store, approval_id, action, "BUDGET_CHANGE", actor)
            _set_caps(store, action, approval_id, actor)
    except approvals.ApprovalError as e:
        approvals.reject(store, approval_id, actor, e.reason)


def _set_caps(store, action, approval_id, actor):
    store.conn.execute("INSERT INTO budget(id, global_cap_cents, per_run_cap_cents, approval_id) VALUES (1,?,?,?) "
                       "ON CONFLICT(id) DO UPDATE SET global_cap_cents=excluded.global_cap_cents, "
                       "per_run_cap_cents=excluded.per_run_cap_cents, approval_id=excluded.approval_id",
                       (action["global_cap_cents"], action["per_run_cap_cents"], approval_id))
    store.event("budget.changed", actor, None, {"approval_id": approval_id, "global_cap_cents": action["global_cap_cents"],
                                                "per_run_cap_cents": action["per_run_cap_cents"]}, refs=[approval_id])
