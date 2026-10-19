"""Command-line interface for the M1 core. Local, offline, synthetic data only.

Human actions take --operator NAME (recorded as human:NAME). The identity is self-declared, not authenticated.
"""
import argparse
import json
import sys

from . import approvals, assessment, budget, diagnose, privacy, workflow
from . import evidence as E
from .export import ExportRefused, export_csv
from .ingest import ImportRejected, import_fixture
from .store import IntegrityError, Store
from .util import load_json


def _actor(args):
    return f"human:{args.operator}" if args.operator else "system"


def _human(args):
    if not args.operator:
        raise SystemExit("this command requires --operator NAME (a human decision)")
    return f"human:{args.operator}"


def _print(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True))


def cmd_init(store, args):
    store.event("integrity.checked", _actor(args), None, {"problems": store.integrity_problems()})
    _print({"db": args.db, "problems": store.integrity_problems()})


def cmd_import(store, args):
    _print(import_fixture(store, load_json(args.file), _actor(args)))


def cmd_evidence_add(store, args):
    data = load_json(args.file)
    results = [E.record(store, ev, _actor(args)) for ev in (data if isinstance(data, list) else [data])]
    _print({"recorded": sum(results), "rejected": len(results) - sum(results)})


def cmd_score(store, args):
    ids = [r[0] for r in store.conn.execute("SELECT lead_id FROM leads ORDER BY lead_id")] if args.lead == "all" \
        else [args.lead]
    _print({i: assessment.score_lead(store, i, _actor(args))["layer3"]["bucket"] for i in ids})


def cmd_leads(store, args):
    rows = []
    for lead in store.docs("leads", "1=1 ORDER BY lead_id"):
        score = store.latest_score(lead["lead_id"])
        rows.append({"lead_id": lead["lead_id"], "state": lead["state"], "version": lead["state_version"],
                     "priority_for_review": score["layer3"]["bucket"] if score else None,
                     "purchase_intent": lead["purchase_intent"]})
    _print(rows)


def cmd_transition(store, args):
    lead = workflow.transition(store, args.lead, args.to, _actor(args), args.expected_version, args.approval)
    _print({"lead_id": lead["lead_id"], "state": lead["state"], "state_version": lead["state_version"]})


def cmd_approve_request(store, args):
    if args.type == "SHORTLIST":
        score = store.latest_score(args.lead)
        if score is None:
            raise SystemExit("no score for this lead")
        action = {"kind": "SHORTLIST", "lead_id": args.lead, "score_id": score["score_id"]}
    else:
        action = budget.change_action(args.global_cap, args.per_run_cap)
    _print(approvals.request(store, args.type, action, _actor(args)))


def cmd_approve_decide(store, args):
    _print(approvals.decide(store, args.approval, args.decision, _human(args), args.comment))


def cmd_approve_list(store, args):
    _print([{k: a[k] for k in ("approval_id", "type", "status", "action", "expires_at")}
            for a in store.docs("approvals", "1=1 ORDER BY approval_id")])


def cmd_budget_show(store, args):
    _print(budget.status(store))


def cmd_budget_apply(store, args):
    budget.apply_change(store, args.approval, args.global_cap, args.per_run_cap, _human(args))
    _print(budget.status(store))


def cmd_tool_call(store, args):
    status, detail, entry = budget.call_tool(store, args.tool, {}, args.run, _actor(args))
    _print({"status": status, "detail": detail, "entry_id": entry["entry_id"]})


def cmd_suppress(store, args):
    _print(privacy.suppress(store, args.lead, args.reason, _human(args)))


def cmd_erase(store, args):
    _print({"erased_evidence": privacy.erase(store, args.lead, _human(args))})


def cmd_retention(store, args):
    _print({"purged_evidence": privacy.retention_run(store, _actor(args))})


def cmd_export(store, args):
    out = args.out or f"exports/leads_SYNTHETIC_{store.now().replace(':', '')}.csv"
    _print(export_csv(store, out, _actor(args)))


def cmd_trace(store, args):
    for ev in store.events(args.lead):
        print(f"{ev['seq']:>5} {ev['ts']} {ev['type']:<26} {ev['actor']['kind'].lower()}:{ev['actor']['id']:<12} "
              f"{json.dumps(ev['payload'], ensure_ascii=False, sort_keys=True)}")


def cmd_diagnose(store, args):
    out = diagnose.diagnose(store, args.site, _actor(args))
    _print({c: r["status"] for c, r in out["results"].items()})


def cmd_verify(store, args):
    problems = store.integrity_problems()
    store.event("integrity.checked", _actor(args), None, {"problems": problems})
    _print({"problems": problems, "events": store.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]})


def parser():
    p = argparse.ArgumentParser(prog="waos", description="Web Agency OS M1 core (offline, synthetic data only)")
    p.add_argument("--db", default="waos.sqlite3")
    p.add_argument("--operator", help="human operator name for decisions (self-declared, not authenticated)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(fn=cmd_init)
    s = sub.add_parser("import"); s.add_argument("file"); s.set_defaults(fn=cmd_import)
    ev = sub.add_parser("evidence").add_subparsers(dest="sub", required=True)
    s = ev.add_parser("add"); s.add_argument("file"); s.set_defaults(fn=cmd_evidence_add)
    s = sub.add_parser("score"); s.add_argument("lead", help="lead id or 'all'"); s.set_defaults(fn=cmd_score)
    sub.add_parser("leads").set_defaults(fn=cmd_leads)
    s = sub.add_parser("transition"); s.add_argument("lead"); s.add_argument("to")
    s.add_argument("--expected-version", type=int); s.add_argument("--approval"); s.set_defaults(fn=cmd_transition)
    ap = sub.add_parser("approve").add_subparsers(dest="sub", required=True)
    s = ap.add_parser("request"); s.add_argument("--type", required=True, choices=approvals.M1_TYPES)
    s.add_argument("--lead"); s.add_argument("--global-cap", type=int); s.add_argument("--per-run-cap", type=int)
    s.set_defaults(fn=cmd_approve_request)
    s = ap.add_parser("decide"); s.add_argument("approval"); s.add_argument("decision", choices=("APPROVED", "REJECTED"))
    s.add_argument("--comment"); s.set_defaults(fn=cmd_approve_decide)
    ap.add_parser("list").set_defaults(fn=cmd_approve_list)
    bu = sub.add_parser("budget").add_subparsers(dest="sub", required=True)
    bu.add_parser("show").set_defaults(fn=cmd_budget_show)
    s = bu.add_parser("apply"); s.add_argument("approval"); s.add_argument("--global-cap", type=int, required=True)
    s.add_argument("--per-run-cap", type=int, required=True); s.set_defaults(fn=cmd_budget_apply)
    to = sub.add_parser("tool").add_subparsers(dest="sub", required=True)
    s = to.add_parser("call"); s.add_argument("tool"); s.add_argument("--run", default="cli"); s.set_defaults(fn=cmd_tool_call)
    s = sub.add_parser("suppress"); s.add_argument("lead")
    s.add_argument("--reason", default="OPT_OUT", choices=("OPT_OUT", "OBJECTION", "ERASURE", "POLICY"))
    s.set_defaults(fn=cmd_suppress)
    s = sub.add_parser("erase"); s.add_argument("lead"); s.set_defaults(fn=cmd_erase)
    re_ = sub.add_parser("retention").add_subparsers(dest="sub", required=True)
    re_.add_parser("run").set_defaults(fn=cmd_retention)
    ex = sub.add_parser("export").add_subparsers(dest="sub", required=True)
    s = ex.add_parser("csv"); s.add_argument("--out"); s.set_defaults(fn=cmd_export)
    s = sub.add_parser("trace"); s.add_argument("lead"); s.set_defaults(fn=cmd_trace)
    sub.add_parser("verify").set_defaults(fn=cmd_verify)
    s = sub.add_parser("diagnose", help="static diagnosis of a LOCAL synthetic site directory")
    s.add_argument("site"); s.set_defaults(fn=cmd_diagnose)
    s = sub.add_parser("demo-m2a", help="fresh database + diagnosis of the whole local corpus + report")
    s.add_argument("--corpus", default="corpus/m2a"); s.add_argument("--out", default="demo_out/m2a")
    s.set_defaults(fn=None)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    if args.cmd == "demo-m2a":
        diagnose.print_report(diagnose.run_demo(args.corpus, args.out))
        return 0
    try:
        store = Store(args.db)
    except IntegrityError as e:
        print(f"refusing to run: database integrity check failed: {e}", file=sys.stderr)
        return 2
    try:
        args.fn(store, args)
    except (workflow.TransitionDenied, approvals.ApprovalError, ImportRejected, ExportRefused,
            diagnose.DiagnosisError) as e:
        print(f"denied: {e}", file=sys.stderr)
        return 3
    finally:
        store.close()
    return 0
