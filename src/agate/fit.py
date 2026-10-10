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

from .policy import PolicyStore, Verdict
from .profiles import HardwareObservation, identify_profile


@dataclass(frozen=True, slots=True)
class FitDecision:
    feasible: bool
    reason_code: str
    model: str
    profile_id: str | None
    verdict: Verdict | None
    overridable: bool = False
    # A fit built from a declared profile id is not measured evidence; this module
    # only ever answers from an observation.
    evidence_class: Literal["observed"] = "observed"


def assess_fit(
    policy: PolicyStore,
    model: str,
    observation: HardwareObservation,
    profile_database: Path | str | None = None,
) -> FitDecision:
    try:
        profile = identify_profile(observation, profile_database)
    except ValueError:
        return FitDecision(False, "profile_ambiguous", model, None, None)
    if profile is None:
        return FitDecision(False, "profile_unidentified", model, None, None)
    verdict = policy.verdict(model, profile)
    if verdict == "NEVER":
        return FitDecision(False, "model_forbidden_on_profile", model, profile.profile_id, verdict)
    return FitDecision(True, f"fit_{verdict.lower()}", model, profile.profile_id, verdict)
