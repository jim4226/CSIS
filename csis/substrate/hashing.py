"""Canonical hashing for hash-preconditioned writes.

Used by: memory store (precondition on promote), capability tag input_hash,
event log chain, Auditor why-doc preconditions, Verifier artifact hashes.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def sha256_hex(data: bytes | str) -> str:
    """Return 64-char hex sha256 of the input."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def canonical_json_hash(obj: Any) -> str:
    """sha256:<hex> of a JSON-canonicalized object (sorted keys, no whitespace).

    Use this anywhere we need a stable hash of a structured value — capability
    tag inputs, memory store contents, artifact bodies. NaN/Infinity are
    rejected to keep the hash stable across runtimes.
    """
    body = json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)
    return "sha256:" + sha256_hex(body)


def hash_artifact(body: bytes | str) -> str:
    """sha256:<hex> of an opaque artifact body (a patch, a proof, raw text)."""
    return "sha256:" + sha256_hex(body)
