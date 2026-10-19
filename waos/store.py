"""SQLite storage: state tables + append-only event log, written in the same transaction (D-022).

Limitations (architecture § 6.3): one writer at a time; triggers protect against program bugs, not against someone
with access to the file; not encrypted at rest — synthetic data only.
"""
import contextlib
import json
import sqlite3

from . import schema
from .util import iso, new_id, utc_now

SCHEMA_VERSION = "m1.1"

STATES = ("DISCOVERED", "NEEDS_REVIEW", "IDENTITY_RESOLVED", "DIAGNOSED", "SCORED", "SHORTLISTED", "PARKED",
          "DISQUALIFIED", "SUPPRESSED", "ON_HOLD")


def _in(values):
    return "(" + ",".join(f"'{v}'" for v in values) + ")"


MODES = _in(("SYNTHETIC", "TEST_FIXTURE"))

DDL = f"""
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS campaigns (
  campaign_id TEXT PRIMARY KEY, data_mode TEXT NOT NULL CHECK (data_mode IN {MODES}), doc TEXT NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS leads (
  lead_id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
  entity_key TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN {_in(STATES)}),
  state_version INTEGER NOT NULL CHECK (state_version >= 0),
  purchase_intent TEXT NOT NULL CHECK (purchase_intent = 'UNKNOWN'),
  suppressed INTEGER NOT NULL CHECK (suppressed IN (0, 1)),
  data_mode TEXT NOT NULL CHECK (data_mode IN {MODES}),
  last_transition_at TEXT NOT NULL,
  doc TEXT NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS captures (
  capture_sha256 TEXT PRIMARY KEY, text TEXT, available INTEGER NOT NULL CHECK (available IN (0, 1))) STRICT;
CREATE TABLE IF NOT EXISTS evidence (
  evidence_id TEXT PRIMARY KEY,
  lead_id TEXT NOT NULL REFERENCES leads(lead_id),
  field TEXT NOT NULL,
  claim_status TEXT NOT NULL CHECK (claim_status IN ('KNOWN','INFERRED','ESTIMATED','UNKNOWN','CONFLICTING')),
  source_class TEXT NOT NULL CHECK (source_class IN ('OFFICIAL','PUBLIC_REGISTRY','MEASUREMENT','PROFESSIONAL_DIRECTORY',
                                                     'SECTOR_SOURCE','OTHER_VERIFIABLE','HUMAN_REVIEW','UNVERIFIED',
                                                     'NOT_FOUND')),
  strength TEXT NOT NULL CHECK (strength IN ('HIGH','MEDIUM','LOW','UNKNOWN')),
  personal_data TEXT NOT NULL CHECK (personal_data IN ('NONE','BUSINESS_CONTACT','OTHER')),
  retention_until TEXT,
  erased INTEGER NOT NULL CHECK (erased IN (0, 1)),
  doc TEXT NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS findings (
  finding_id TEXT PRIMARY KEY,
  lead_id TEXT NOT NULL REFERENCES leads(lead_id),
  code TEXT NOT NULL,
  technical_severity TEXT NOT NULL CHECK (technical_severity IN ('CRITICAL','MAJOR','MINOR','INFO')),
  claim_status TEXT NOT NULL CHECK (claim_status IN ('KNOWN','INFERRED','UNKNOWN')),
  doc TEXT NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS scores (
  score_id TEXT PRIMARY KEY,
  lead_id TEXT NOT NULL REFERENCES leads(lead_id),
  rules_hash TEXT NOT NULL,
  bucket TEXT NOT NULL CHECK (bucket IN ('REVIEW_PRIORITY','WATCH','LOW','PENDING','DISQUALIFIED')),
  computed_at TEXT NOT NULL,
  doc TEXT NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS approvals (
  approval_id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  action_sha256 TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('PENDING','APPROVED','REJECTED','EXPIRED','EXECUTED')),
  execution_count INTEGER NOT NULL CHECK (execution_count IN (0, 1)),
  doc TEXT NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS ledger (
  entry_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  tool TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('OK','DENIED','ERROR')),
  actual_cents INTEGER NOT NULL CHECK (actual_cents >= 0),
  doc TEXT NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS budget (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  global_cap_cents INTEGER NOT NULL CHECK (global_cap_cents >= 0),
  per_run_cap_cents INTEGER NOT NULL CHECK (per_run_cap_cents >= 0),
  approval_id TEXT NOT NULL REFERENCES approvals(approval_id)) STRICT;
CREATE TABLE IF NOT EXISTS suppressions (
  suppression_id TEXT PRIMARY KEY,
  reason TEXT NOT NULL CHECK (reason IN ('OPT_OUT','OBJECTION','ERASURE','POLICY')),
  doc TEXT NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS suppression_hashes (
  hash TEXT PRIMARY KEY, suppression_id TEXT NOT NULL REFERENCES suppressions(suppression_id)) STRICT;
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL UNIQUE,
  ts TEXT NOT NULL,
  type TEXT NOT NULL,
  actor_kind TEXT NOT NULL CHECK (actor_kind IN ('SYSTEM','HUMAN','AGENT')),
  actor_id TEXT NOT NULL,
  lead_id TEXT,
  doc TEXT NOT NULL) STRICT;
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
  BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
  BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
"""

REQUIRED_TRIGGERS = ("events_no_update", "events_no_delete")
REQUIRED_TABLES = ("meta", "campaigns", "leads", "captures", "evidence", "findings", "scores", "approvals", "ledger",
                   "budget", "suppressions", "suppression_hashes", "events")


class IntegrityError(Exception):
    pass


def actor_of(actor):
    """'system' | 'human:<id>' | 'agent:<id>' → event actor dict."""
    if actor == "system":
        return {"kind": "SYSTEM", "id": "waos"}
    kind, _, ident = actor.partition(":")
    if kind not in ("human", "agent") or not ident:
        raise ValueError(f"invalid actor {actor!r}")
    return {"kind": kind.upper(), "id": ident}


class Store:
    def __init__(self, path, clock=None, migrate=True):
        self.path = path
        self.clock = clock or utc_now
        self.conn = sqlite3.connect(path, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        initialized = self.conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone()
        if migrate and not initialized:          # an existing database is checked, never silently repaired
            self.migrate()
        problems = self.integrity_problems()
        if problems:
            self.conn.close()
            raise IntegrityError("; ".join(problems))

    # ── schema
    def migrate(self):
        self.conn.executescript(DDL)
        self.conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)", (SCHEMA_VERSION,))

    def integrity_problems(self):
        problems = []
        names = {r["name"] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','trigger')")}
        problems += [f"missing table {t}" for t in REQUIRED_TABLES if t not in names]
        problems += [f"missing trigger {t}" for t in REQUIRED_TRIGGERS if t not in names]
        if self.conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            problems.append("foreign keys disabled")
        if "meta" in names:
            row = self.conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            if not row or row[0] != SCHEMA_VERSION:
                problems.append("schema version mismatch")
        return problems

    def close(self):
        self.conn.close()

    def now(self):
        return iso(self.clock())

    @contextlib.contextmanager
    def tx(self):
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self.conn
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")

    # ── events
    def event(self, type_, actor, lead_id=None, payload=None, refs=(), causation_id=None, correlation_id=None):
        doc = {"schema_version": "waos.event.v1", "event_id": new_id("evt_"), "ts": self.now(), "type": type_,
               "actor": actor_of(actor), "lead_id": lead_id, "subject_refs": list(refs),
               "causation_id": causation_id, "correlation_id": correlation_id, "payload": payload or {}}
        schema.validate("event", doc)
        self.conn.execute("INSERT INTO events(event_id, ts, type, actor_kind, actor_id, lead_id, doc) "
                          "VALUES (?,?,?,?,?,?,?)",
                          (doc["event_id"], doc["ts"], type_, doc["actor"]["kind"], doc["actor"]["id"], lead_id,
                           json.dumps(doc, ensure_ascii=False)))
        return doc["event_id"]

    def events(self, lead_id=None):
        sql, args = "SELECT seq, doc FROM events", ()
        if lead_id:
            sql, args = sql + " WHERE lead_id = ?", (lead_id,)
        out = []
        for row in self.conn.execute(sql + " ORDER BY seq", args):
            doc = json.loads(row["doc"])
            doc["seq"] = row["seq"]
            out.append(doc)
        return out

    # ── documents
    def doc(self, table, key_col, key):
        row = self.conn.execute(f"SELECT doc FROM {table} WHERE {key_col} = ?", (key,)).fetchone()
        return json.loads(row["doc"]) if row else None

    def docs(self, table, where="1=1", args=()):
        return [json.loads(r["doc"]) for r in self.conn.execute(f"SELECT doc FROM {table} WHERE {where}", args)]

    def lead(self, lead_id):
        return self.doc("leads", "lead_id", lead_id)

    def put_lead(self, lead, last_transition_at=None, insert=False):
        schema.validate("lead", lead)
        cols = (lead["lead_id"], lead["campaign_id"], lead["entity_key"], lead["state"], lead["state_version"],
                lead["purchase_intent"], int(lead["suppressed"]), lead["data_mode"],
                last_transition_at or self.now(), json.dumps(lead, ensure_ascii=False))
        if insert:
            self.conn.execute("INSERT INTO leads(lead_id, campaign_id, entity_key, state, state_version, purchase_intent,"
                              " suppressed, data_mode, last_transition_at, doc) VALUES (?,?,?,?,?,?,?,?,?,?)", cols)
        else:
            self.conn.execute("UPDATE leads SET campaign_id=?, entity_key=?, state=?, state_version=?, purchase_intent=?,"
                              " suppressed=?, data_mode=?, last_transition_at=?, doc=? WHERE lead_id=?",
                              cols[1:] + (cols[0],))

    def last_transition_at(self, lead_id):
        return self.conn.execute("SELECT last_transition_at FROM leads WHERE lead_id=?", (lead_id,)).fetchone()[0]

    def campaign(self, campaign_id):
        return self.doc("campaigns", "campaign_id", campaign_id)

    def evidence_for(self, lead_id):
        return self.docs("evidence", "lead_id = ? ORDER BY evidence_id", (lead_id,))

    def put_evidence(self, ev, insert=True):
        schema.validate("evidence", ev)
        cols = (ev["evidence_id"], ev["subject"]["lead_id"], ev["field"], ev["claim_status"], ev["source_class"],
                ev["strength"], ev["personal_data"], ev.get("retention_until"), int(ev["erased"]),
                json.dumps(ev, ensure_ascii=False))
        if insert:
            self.conn.execute("INSERT INTO evidence(evidence_id, lead_id, field, claim_status, source_class, strength,"
                              " personal_data, retention_until, erased, doc) VALUES (?,?,?,?,?,?,?,?,?,?)", cols)
        else:
            self.conn.execute("UPDATE evidence SET lead_id=?, field=?, claim_status=?, source_class=?, strength=?,"
                              " personal_data=?, retention_until=?, erased=?, doc=? WHERE evidence_id=?",
                              cols[1:] + (cols[0],))

    def findings_for(self, lead_id):
        return self.docs("findings", "lead_id = ? ORDER BY finding_id", (lead_id,))

    def capture_text(self, sha):
        row = self.conn.execute("SELECT text, available FROM captures WHERE capture_sha256=?", (sha,)).fetchone()
        return row["text"] if row and row["available"] else None

    def latest_score(self, lead_id):
        row = self.conn.execute("SELECT doc FROM scores WHERE lead_id=? ORDER BY computed_at DESC, rowid DESC LIMIT 1",
                                (lead_id,)).fetchone()
        return json.loads(row["doc"]) if row else None
