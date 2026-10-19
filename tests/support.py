import copy
import datetime as dt
import os
import shutil
import tempfile
import unittest

from waos import approvals, assessment, workflow
from waos.ingest import import_fixture
from waos.store import Store
from waos.util import ROOT, load_json

from . import ATTEMPTS

T0 = dt.datetime(2026, 10, 19, 9, 0, 0, tzinfo=dt.timezone.utc)
DEMO = load_json(os.path.join(ROOT, "fixtures", "synthetic_demo.json"))
OPERATOR = "human:test_operator"


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, **kwargs):
        self.t += dt.timedelta(**kwargs)


def demo():
    return copy.deepcopy(DEMO)


def personal_values(fixture=None):
    """Every synthetic personal value in the demo fixture (business contact data)."""
    out = set()
    for entry in (fixture or DEMO)["leads"]:
        b = entry["lead"]["business"]
        out |= {b.get(k) for k in ("phone", "email", "owner_name") if b.get(k)}
        out |= {e["value"] for e in entry.get("evidence", []) if e.get("personal_data", "NONE") != "NONE"}
    return out


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="waos-test-")
        self.db = os.path.join(self.tmp, "t.sqlite3")
        self.clock = Clock()
        self.store = Store(self.db, clock=self.clock)
        self.attempts_before = len(ATTEMPTS)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.assertEqual(len(ATTEMPTS), self.attempts_before, "a network access was attempted")

    def tick(self, seconds=1):
        self.clock.advance(seconds=seconds)

    def load_demo(self):
        return import_fixture(self.store, demo())

    def to_scored(self, lead_id):
        """DISCOVERED → IDENTITY_RESOLVED → DIAGNOSED → SCORED, ticking the clock between steps."""
        for to in ("IDENTITY_RESOLVED", "DIAGNOSED"):
            workflow.transition(self.store, lead_id, to, "system")
            self.tick()
        assessment.score_lead(self.store, lead_id)
        self.tick()
        workflow.transition(self.store, lead_id, "SCORED", "system")
        self.tick()

    def shortlist_approval(self, lead_id, decision="APPROVED"):
        score = self.store.latest_score(lead_id)
        action = {"kind": "SHORTLIST", "lead_id": lead_id, "score_id": score["score_id"]}
        doc = approvals.request(self.store, "SHORTLIST", action, "system")
        approvals.decide(self.store, doc["approval_id"], decision, OPERATOR)
        return doc["approval_id"], action

    def events_of(self, type_, lead_id=None):
        return [e for e in self.store.events(lead_id) if e["type"] == type_]
