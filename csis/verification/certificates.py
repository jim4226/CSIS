"""VerifierCertificate construction + cross-checkpoint enforcement.

F1 mitigation (mock-vs-mock theatre): the certificate records the structural
identity of both checkpoints — model_id, tool_set, backend, checkpoint label.
Build rejects when these are identical between builder and verifier sides.

This module is the gate between V1+V2 outputs and the Auditor. If the
cert build raises, the iteration is rolled back and a `verifier.reject`
event is emitted with the reason.
"""
from __future__ import annotations

import time
import uuid
from typing import Iterable

from csis.contracts import (
    Artifact,
    CriticFinding,
    GraderResult,
    Plan,
    VerifierCertificate,
)


class CrossCheckpointViolation(Exception):
    """Raised when builder + verifier identities are insufficiently distinct.

    F1: at least two of {model_id, tool_set, backend} must differ. A
    checkpoint_id-only difference is decorative.

    P3 (cycle 2): the diff is computed strictly over REQUIRED_IDENTITY_KEYS.
    A backend that omits a required key now FAILS the check rather than
    earning free diffs from missing-key positions.

    Vf1 (cycle 10): ``checkpoint_id`` is EXCLUDED from the distinctness
    count — it is unique by construction (every checkpoint has a distinct
    label) and carries no structural information about whether two real,
    differing models/tools/backends are involved. Counting it let the
    classic spoof (rename "builder" -> "auditor", which by default mirrors
    into ``model_id``) clear a 2-of-4 bar while a single backend
    self-confirmed. The count now runs over the SUBSTANTIVE keys only, and
    an identity whose ``model_id`` equals its ``checkpoint_id`` (the
    un-overridden default) is rejected as "model identity not declared".
    """


class IdentityShapeViolation(Exception):
    """Raised when an identity dict is missing required keys (P3 mitigation)."""


class GraderDriftViolation(Exception):
    """Raised when one or more pinned grader source hashes have drifted
    between pin time and verification time. F6 mitigation."""


# P3 mitigation: every backend.checkpoint_identity() MUST return at least
# these keys. The set-union heuristic from cycle 1 let a partial dict
# silently earn diffs via missing-key positions; this guard kills that.
REQUIRED_IDENTITY_KEYS: frozenset[str] = frozenset(
    {"checkpoint_id", "model_id", "tool_set", "backend"}
)

# Vf1 (cycle 10): the keys that carry real structural meaning about whether
# two DISTINCT checkpoints are involved. ``checkpoint_id`` is unique by
# construction (it is just the label) so it is excluded — a label rename
# must not, on its own, satisfy the cross-checkpoint bar.
SUBSTANTIVE_IDENTITY_KEYS: frozenset[str] = REQUIRED_IDENTITY_KEYS - {"checkpoint_id"}


def _validate_identity_shape(name: str, identity: dict[str, str]) -> None:
    missing = REQUIRED_IDENTITY_KEYS - set(identity)
    if missing:
        raise IdentityShapeViolation(
            f"{name} identity is missing required key(s): {sorted(missing)}. "
            f"Got keys: {sorted(identity)}. See cycle-2 finding P3."
        )


def _assert_model_declared(name: str, identity: dict[str, str]) -> None:
    """Vf1 (cycle 10): reject the un-overridden default identity.

    ``LLMBackend.checkpoint_identity`` defaults ``model_id`` to the
    ``checkpoint_id`` argument. An identity where they are still equal means
    the backend never asserted a real model id — so a builder-checkpoint
    rename would flip BOTH fields in lockstep and spoof distinctness. Force
    backends to declare a structurally-meaningful model id.
    """
    if identity.get("model_id") == identity.get("checkpoint_id"):
        raise CrossCheckpointViolation(
            f"{name} model identity not declared: model_id == checkpoint_id "
            f"({identity.get('checkpoint_id')!r}). A backend must assert a real "
            f"model id (e.g. via set_model_id / an overridden checkpoint_identity) "
            f"so cross-checkpoint separation is not spoofable by a label rename. "
            f"See cycle-10 finding Vf1."
        )


def _identity_diff_count(a: dict[str, str], b: dict[str, str]) -> int:
    # Vf1: compare ONLY the substantive keys (model_id, tool_set, backend).
    # checkpoint_id is excluded — a label-only rename earns zero diffs.
    # P3: missing keys are no longer a free diff (shape is validated first).
    return sum(1 for k in SUBSTANTIVE_IDENTITY_KEYS if a.get(k) != b.get(k))


def assert_cross_checkpoint(
    builder_identity: dict[str, str],
    verifier_identity: dict[str, str],
    *,
    min_distinct_components: int = 2,
) -> None:
    """F1 enforcement: identities must differ in ≥N SUBSTANTIVE components.

    P3: requires both identity dicts to carry every key in
    REQUIRED_IDENTITY_KEYS; diff is computed over the substantive subset only.

    Vf1 (cycle 10): ``checkpoint_id`` no longer counts toward the diff (a
    label rename is decorative), and each side must declare a real model id
    (``model_id != checkpoint_id``). Together these close the one-backend
    self-confirmation spoof: renaming "builder" -> "auditor" flips only the
    label (0 substantive diffs) and leaves ``model_id == checkpoint_id``.
    """
    _validate_identity_shape("builder", builder_identity)
    _validate_identity_shape("verifier", verifier_identity)
    _assert_model_declared("builder", builder_identity)
    _assert_model_declared("verifier", verifier_identity)
    # Vf1 (cycle-10, integration refinement): the BINDING cross-checkpoint
    # guarantee is a DIFFERENT MODEL. The architecture runs the verifier on a
    # structurally different checkpoint (Sonnet-class) than the builder
    # (Opus-class) precisely so the producer cannot rubber-stamp its own work
    # — the distinction that matters is the model. The real AnthropicBackend
    # reports the SAME `backend` ("anthropic") and the SAME `tool_set`
    # ("anthropic-native") for every checkpoint (see anthropic.py), so in
    # production a different `model_id` is the ONLY — and sufficient — signal.
    # Requiring a second substantive axis (the cycle-10 first cut) would
    # reject the real Opus/Sonnet config and the loop could never promote.
    # `_assert_model_declared` above already kills the spoof this finding was
    # about (model_id mirroring a renamed checkpoint_id); here we require the
    # two declared models to actually differ.
    if builder_identity.get("model_id") == verifier_identity.get("model_id"):
        raise CrossCheckpointViolation(
            f"same model on both checkpoints: builder and verifier both report "
            f"model_id={builder_identity.get('model_id')!r}. The verifier must "
            f"run a different model so the builder cannot rubber-stamp its own "
            f"artifact (F1 / cycle-10 Vf1). "
            f"builder={builder_identity} verifier={verifier_identity}"
        )
    # `min_distinct_components` is retained for signature compatibility; the
    # model-differs rule above is the binding check. A second differing axis
    # (tool_set/backend) is welcome defense-in-depth but not required, since
    # the production backend cannot provide one.
    _ = (min_distinct_components, _identity_diff_count)


# Vf7 (cycle 10): attempt strings that carry no real falsification work and
# must not count toward the min-attempts floor. "<unspecified>" is the
# sentinel the forgiving critic parser inserts when an item omits "attempt".
_TRIVIAL_ATTEMPT_TOKENS: frozenset[str] = frozenset({"", "<unspecified>"})


def _count_substantive_attempts(critic_findings: Iterable[CriticFinding]) -> int:
    """Count DISTINCT, non-trivial critic attempts (Vf7 mitigation).

    The min-attempts floor exists to force the Critic to do N independent
    pieces of falsification work. Cardinality alone is gameable: three
    identical `{"attempt":"same"}`, or three blank/`<unspecified>` attempts,
    satisfied `len(findings) >= min` with no real adversarial effort. We
    dedupe on the (whitespace-normalized) attempt string and drop blank /
    sentinel attempts before counting.
    """
    seen: set[str] = set()
    for f in critic_findings:
        key = (f.attempt or "").strip()
        if key.lower() in _TRIVIAL_ATTEMPT_TOKENS:
            continue
        seen.add(key)
    return len(seen)


def build_certificate(
    *,
    plan: Plan,
    artifact: Artifact,
    builder_identity: dict[str, str],
    verifier_identity: dict[str, str],
    grader_results: list[GraderResult],
    critic_findings: list[CriticFinding],
    grader_drift: Iterable[str] = (),
    min_critic_attempts: int = 3,
) -> VerifierCertificate:
    """Build a VerifierCertificate. Raises on cross-checkpoint or grader-drift
    violations. The cert's `passed` field is the AND of: every grader passed,
    no critic finding is `falsified=True`, and minimum critic attempts met."""
    assert_cross_checkpoint(builder_identity, verifier_identity)

    drift_list = list(grader_drift)
    if drift_list:
        raise GraderDriftViolation(
            f"pinned graders drifted between pin and verify: {drift_list}. "
            f"See red-team finding F6."
        )

    all_pass = all(g.passed for g in grader_results)
    any_falsified = any(f.falsified for f in critic_findings)
    # Vf7 (cycle 10): the min-attempts floor must measure REAL work, not
    # cardinality. Three identical {"attempt":"same"} (or blank /
    # "<unspecified>" attempts that the forgiving parser fills in) used to
    # satisfy min=3. Count DISTINCT, non-trivial attempt strings instead.
    n_substantive_attempts = _count_substantive_attempts(critic_findings)
    enough_attempts = n_substantive_attempts >= min_critic_attempts

    passed = all_pass and (not any_falsified) and enough_attempts

    notes_parts: list[str] = []
    if not all_pass:
        failed = [g.grader for g in grader_results if not g.passed]
        notes_parts.append(f"v1_failed={failed}")
    if any_falsified:
        falsified_attempts = [f.attempt for f in critic_findings if f.falsified]
        notes_parts.append(f"v2_falsified={falsified_attempts}")
    if not enough_attempts:
        notes_parts.append(
            f"critic produced {n_substantive_attempts} distinct substantive "
            f"attempts ({len(critic_findings)} raw), minimum {min_critic_attempts}"
        )

    return VerifierCertificate(
        cert_id=f"cert-{uuid.uuid4().hex[:12]}",
        plan_id=plan.plan_id,
        artifact_id=artifact.artifact_id,
        artifact_hash=artifact.body_hash,
        builder_checkpoint=builder_identity.get("checkpoint_id", "unknown"),
        verifier_checkpoint=verifier_identity.get("checkpoint_id", "unknown"),
        grader_results=grader_results,
        critic_findings=critic_findings,
        passed=passed,
        signed_at=time.time(),
        notes="; ".join(notes_parts) if notes_parts else "all-clear",
    )
