"""Measured model fit for runtime admission (R4 T1).

Admission needs one answer from Agate: can this model run on the hardware that was
actually observed? The answer is built only from existing pieces -- an observation is
matched to exactly one maintained profile, then the policy verdict for that profile is
read. It does not decide the open five-evidence-plane record or PROFILE_UNDERUSE.

Fail closed: missing or ambiguous evidence is infeasible, never a default allow, and an
impossible fit (NEVER, or a model absent from policy) is not overridable by a human.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .evidence import FitEvidence
from .policy import PolicyStore, Verdict
from .profiles import HardwareObservation, _matches, load_profile_store


@dataclass(frozen=True, slots=True)
class FitDecision:
    """Measured fit verdict with a reason and an overridable flag."""
    feasible: bool
    reason_code: str
    model: str
    profile_id: str | None
    verdict: Verdict | None
    # Placement evidence never confers an authorization capability or claim.
    evidence_class: Literal["observed", "derived"]
    overridable: bool = False


def assess_fit(
    policy: PolicyStore,
    model: str,
    observation: HardwareObservation,
    evidence: FitEvidence,
    profile_database: Path | str | None = None,
) -> FitDecision:
    """Assess a model against measured hardware evidence; refuse when evidence is missing."""
    if not evidence.covers(observation):
        raise ValueError("fit evidence does not cover the assessed hardware observation")
    # Load first so a broken or unsupported database raises to the caller instead of
    # being mistaken for ambiguous hardware evidence.
    store = load_profile_store(profile_database)
    matches = [p for p in store.profiles.values() if _matches(p, observation)]
    if len(matches) > 1:
        return FitDecision(
            False, "profile_ambiguous", model, None, None,
            evidence_class=evidence.classification,
        )
    if not matches:
        return FitDecision(
            False, "profile_unidentified", model, None, None,
            evidence_class=evidence.classification,
        )
    profile = matches[0]
    verdict = policy.verdict(model, profile)
    if verdict == "NEVER":
        return FitDecision(
            False, "model_forbidden_on_profile", model, profile.profile_id, verdict,
            evidence_class=evidence.classification,
        )
    return FitDecision(
        True, f"fit_{verdict.lower()}", model, profile.profile_id, verdict,
        evidence_class=evidence.classification,
    )
