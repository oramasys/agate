"""R4 T1: Agate's measured-fit answer for admission. Impossible hardware is
non-overridable, and missing or ambiguous evidence refuses rather than allows."""
from __future__ import annotations

import pytest

from agate import HardwareObservation, load_policy, load_profile_store
from agate.fit import FitDecision, assess_fit


def observation_for(profile_id: str) -> HardwareObservation:
    profile = load_profile_store().profiles[profile_id]
    m = profile.match
    return HardwareObservation(
        os=m.get("os", profile.os),
        cpu=m.get("cpu_contains", profile.cpu),
        ram_gb=m.get("ram_gb", profile.ram_gb),
        accelerator=m.get("accelerator_contains", profile.accelerator),
        accelerator_memory_gb=m.get("accelerator_memory_gb", profile.accelerator_memory_gb),
    )


def pick(policy, profile_id: str, wanted: set[str]) -> str | None:
    profile = load_profile_store().profiles[profile_id]
    for name, spec in policy.models.items():
        if spec.verdict_for_tier(profile.verdict_tier) in wanted:
            return name
    return None


@pytest.fixture(scope="module")
def policy():
    return load_policy()


def profiles_with(policy, wanted: set[str]):
    for profile_id in load_profile_store().profiles:
        model = pick(policy, profile_id, wanted)
        if model is not None:
            return profile_id, model
    pytest.skip(f"no profile/model pair with verdict {wanted}")


def test_measured_fit_allows_a_permitted_model(policy):
    profile_id, model = profiles_with(policy, {"PREFER", "ALLOW"})
    decision = assess_fit(policy, model, observation_for(profile_id))
    assert isinstance(decision, FitDecision)
    assert decision.feasible
    assert decision.profile_id == profile_id
    assert decision.evidence_class == "observed"
    assert decision.reason_code in {"fit_prefer", "fit_allow"}


def test_forbidden_model_is_infeasible_and_not_overridable(policy):
    profile_id, model = profiles_with(policy, {"NEVER"})
    decision = assess_fit(policy, model, observation_for(profile_id))
    assert not decision.feasible
    assert not decision.overridable
    assert decision.reason_code == "model_forbidden_on_profile"


def test_unknown_model_is_infeasible(policy):
    profile_id = next(iter(load_profile_store().profiles))
    decision = assess_fit(policy, "no-such-model", observation_for(profile_id))
    assert not decision.feasible
    assert not decision.overridable


def test_missing_evidence_refuses_rather_than_defaulting(policy):
    decision = assess_fit(policy, "any", HardwareObservation())
    assert not decision.feasible
    assert decision.reason_code == "profile_unidentified"
    assert decision.profile_id is None
    assert not decision.overridable


def test_ambiguous_evidence_refuses(policy, monkeypatch):
    import agate.fit as fit

    def ambiguous(_obs, _path=None):
        raise ValueError("hardware observation matches multiple profiles")

    monkeypatch.setattr(fit, "identify_profile", ambiguous)
    decision = assess_fit(policy, "any", HardwareObservation(os="macOS"))
    assert not decision.feasible
    assert decision.reason_code == "profile_ambiguous"
