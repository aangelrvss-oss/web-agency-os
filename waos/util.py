"""Small shared helpers: paths, canonical JSON, hashing, ids, clock."""
import datetime as dt
import hashlib
import json
import os
import secrets

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACTS = os.path.join(ROOT, "contracts")
RULES = os.path.join(ROOT, "rules")
CONFIG = os.path.join(ROOT, "config")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def canonical(obj):
    """Canonical JSON: UTF-8, sorted keys, no insignificant whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_obj(obj):
    return sha256_text(canonical(obj))


def new_id(prefix):
    """Time-ordered id: prefix + 12 hex chars of milliseconds + 10 random hex chars."""
    ms = int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    return f"{prefix}{ms:012x}{secrets.token_hex(5)}"


def utc_now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso(t):
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


def parse_date(s):
    return dt.datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
