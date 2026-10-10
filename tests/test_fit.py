"""R4 T1: Agate's measured-fit answer for admission. Impossible hardware is
non-overridable, and missing or ambiguous evidence refuses rather than allows."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from agate import HardwareObservation, load_policy, load_profile_store
from agate.evidence import FitEvidence
from agate.fit import FitDecision, assess_fit


def observation_for(profile_id: str) -> HardwareObservation:
    """Test helper: observation for."""
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
    """Test helper: pick."""
    profile = load_profile_store().profiles[profile_id]
    for name, spec in policy.models.items():
        if spec.verdict_for_tier(profile.verdict_tier) in wanted:
            return name
    return None


@pytest.fixture(scope="module")
def policy():
    """Test helper: policy."""
    return load_policy()


def profiles_with(policy, wanted: set[str]):
    """Test helper: profiles with."""
    for profile_id in load_profile_store().profiles:
        model = pick(policy, profile_id, wanted)
        if model is not None:
            return profile_id, model
    pytest.skip(f"no profile/model pair with verdict {wanted}")


def test_measured_fit_allows_a_permitted_model(policy):
    """Measured fit allows a permitted model."""
    profile_id, model = profiles_with(policy, {"PREFER", "ALLOW"})
    observation = observation_for(profile_id)
    decision = assess_fit(
        policy, model, observation, evidence=FitEvidence.derived(observation)
    )
    assert isinstance(decision, FitDecision)
    assert decision.feasible
    assert decision.profile_id == profile_id
    assert decision.evidence_class == "derived"
    assert decision.reason_code in {"fit_prefer", "fit_allow"}


def test_forbidden_model_is_infeasible_and_not_overridable(policy):
    """Forbidden model is infeasible and not overridable."""
    profile_id, model = profiles_with(policy, {"NEVER"})
    observation = observation_for(profile_id)
    decision = assess_fit(
        policy, model, observation, evidence=FitEvidence.derived(observation)
    )
    assert not decision.feasible
    assert not decision.overridable
    assert decision.reason_code == "model_forbidden_on_profile"


def test_unknown_model_is_infeasible(policy):
    """Unknown model is infeasible."""
    profile_id = next(iter(load_profile_store().profiles))
    observation = observation_for(profile_id)
    decision = assess_fit(
        policy, "no-such-model", observation, evidence=FitEvidence.derived(observation)
    )
    assert not decision.feasible
    assert not decision.overridable


def test_missing_evidence_refuses_rather_than_defaulting(policy):
    """Missing evidence refuses rather than defaulting."""
    observation = HardwareObservation()
    decision = assess_fit(
        policy, "any", observation, evidence=FitEvidence.derived(observation)
    )
    assert not decision.feasible
    assert decision.reason_code == "profile_unidentified"
    assert decision.profile_id is None
    assert not decision.overridable


def test_ambiguous_evidence_refuses(policy, monkeypatch):
    """Ambiguous evidence refuses."""
    import agate.fit as fit

    monkeypatch.setattr(fit, "_matches", lambda _profile, _obs: True)  # every profile matches
    observation = HardwareObservation(os="macOS")
    decision = assess_fit(
        policy, "any", observation, evidence=FitEvidence.derived(observation)
    )
    assert not decision.feasible
    assert decision.reason_code == "profile_ambiguous"


def test_broken_profile_database_is_an_error_not_ambiguity(policy, tmp_path):
    """Broken profile database is an error not ambiguity."""
    bad = tmp_path / "profiles.json"
    bad.write_text('{"version": 999, "profiles": []}', encoding="utf-8")
    observation = HardwareObservation(os="macOS")
    with pytest.raises(ValueError):
        assess_fit(
            policy,
            "any",
            observation,
            evidence=FitEvidence.derived(observation),
            profile_database=bad,
        )


def test_unattested_hardware_observation_is_derived_not_observed(policy):
    """Unattested hardware observation is derived not observed."""
    profile_id, model = profiles_with(policy, {"PREFER", "ALLOW"})
    observation = observation_for(profile_id)
    decision = assess_fit(
        policy, model, observation, evidence=FitEvidence.derived(observation)
    )
    assert decision.evidence_class == "derived"


def test_collector_evidence_binds_the_observation_digest():
    """Collector evidence binds the observation digest."""
    observation = observation_for(next(iter(load_profile_store().profiles)))
    clock = lambda: datetime(2026, 10, 11, tzinfo=timezone.utc)
    evidence = FitEvidence.observed(
        observation, collector="local-hardware-collector", clock=clock
    )
    changed = replace(observation, ram_gb=observation.ram_gb + 1)
    assert not evidence.covers(changed)


def test_fit_decision_has_no_capability_or_claim_operation(policy):
    """Fit decision has no capability or claim operation."""
    profile_id, model = profiles_with(policy, {"PREFER", "ALLOW"})
    observation = observation_for(profile_id)
    decision = assess_fit(
        policy, model, observation, evidence=FitEvidence.derived(observation)
    )
    assert not hasattr(decision, "capability")
    assert not hasattr(decision, "principal")
