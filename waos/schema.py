"""Minimal JSON Schema subset validator (standard library only; PD-02 option a).

Supported keywords: type, enum, const, required, properties, additionalProperties, items, minLength, maxLength,
minimum, maximum, pattern, allOf, anyOf, not, if/then/else. Unsupported keywords raise, so a schema cannot silently
rely on something that is not checked.
"""
import os
import re

from .util import CONTRACTS, load_json

SUPPORTED = {"$schema", "$id", "title", "description", "type", "enum", "const", "required", "properties",
             "additionalProperties", "items", "minLength", "maxLength", "minimum", "maximum", "pattern",
             "allOf", "anyOf", "not", "if", "then", "else"}

_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


class ValidationError(Exception):
    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = errors


def _check(schema, value, path, errors):
    unknown = set(schema) - SUPPORTED
    if unknown:
        raise ValueError(f"unsupported schema keywords at {path or '/'}: {sorted(unknown)}")
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_TYPES[t](value) for t in types):
            errors.append(f"{path or '/'}: expected {types}")
            return
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path or '/'}: must be {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path or '/'}: {value!r} not in {schema['enum']}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path or '/'}: shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path or '/'}: longer than {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path or '/'}: does not match {schema['pattern']}")
    if _TYPES["number"](value):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path or '/'}: below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path or '/'}: above {schema['maximum']}")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}/{key}: required")
        props = schema.get("properties", {})
        for key, sub in props.items():
            if key in value:
                _check(sub, value[key], f"{path}/{key}", errors)
        extra = schema.get("additionalProperties", True)
        for key in value:
            if key in props:
                continue
            if extra is False:
                errors.append(f"{path}/{key}: not allowed")
            elif isinstance(extra, dict):
                _check(extra, value[key], f"{path}/{key}", errors)
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            _check(schema["items"], item, f"{path}/{i}", errors)
    for sub in schema.get("allOf", []):
        _check(sub, value, path, errors)
    if "anyOf" in schema and not any(_ok(sub, value) for sub in schema["anyOf"]):
        errors.append(f"{path or '/'}: matches none of anyOf")
    if "not" in schema and _ok(schema["not"], value):
        errors.append(f"{path or '/'}: must not match 'not' schema")
    if "if" in schema:
        branch = schema.get("then") if _ok(schema["if"], value) else schema.get("else")
        if branch:
            _check(branch, value, path, errors)


def _ok(schema, value):
    errors = []
    _check(schema, value, "", errors)
    return not errors


def errors_for(schema, value):
    errors = []
    _check(schema, value, "", errors)
    return errors


_CACHE = {}


def contract(name):
    if name not in _CACHE:
        _CACHE[name] = load_json(os.path.join(CONTRACTS, f"waos.{name}.v1.schema.json"))
    return _CACHE[name]


def validate(name, value):
    errors = errors_for(contract(name), value)
    if errors:
        raise ValidationError([f"{name}: {e}" for e in errors])
    return value


CONTRACT_NAMES = ("lead", "evidence", "finding", "score", "event", "approval", "ledger_entry", "suppression")
