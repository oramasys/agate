"""Agate's model-hardware policy engine.

Loads a schema-conformant model_hardware_policy.yml (schemas/
model_hardware_policy.schema.json, v1) and answers PREFER / ALLOW /
NEVER for a given physical profile and model.

Scope, stated explicitly rather than left implicit: this module answers
the schema's existing three-tier question (mac / windows / shared). It
does not yet implement the full five-evidence-plane decision record or
the PROFILE_UNDERUSE reason code from the synthesized migration plan --
those require decisions (the "too small" verdict's exact shape, whether
machine-level concurrency safety belongs in agate's public contract)
that were explicitly left open for the repo owner, not decided here.
This is a first, real implementation of the part of the contract that
was already fully specified, not a claim that agate's full design is
finished.
"""
from __future__ import annotations

import functools
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Literal

import yaml

from .profiles import HardwareProfile, get_profile

Verdict = Literal["PREFER", "ALLOW", "NEVER"]

_DEFAULT_POLICY_RESOURCE = "data/model_hardware_policy.yml"
_VALID_VERDICTS = frozenset({"PREFER", "ALLOW", "NEVER"})


class HardwareAffinityError(RuntimeError):
    """Raised when a NEVER-verdict model is used on a hardware profile.

    Matches the exception name agate's own README already documents as
    the intended runtime behavior for a NEVER verdict.
    """

    def __init__(self, model: str, profile_id: str, notes: str | None = None):
        self.model = model
        self.profile_id = profile_id
        message = f"model {model!r} is forbidden (NEVER) on hardware profile {profile_id!r}"
        if notes:
            message += f": {notes}"
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ModelSpec:
    name: str
    mac: Verdict
    windows: Verdict
    shared: Verdict
    context: int | None = None
    roles: tuple[str, ...] = ()
    notes: str | None = None

    def verdict_for_tier(self, tier: str) -> Verdict:
        try:
            return getattr(self, tier)
        except AttributeError:
            raise ValueError(f"unknown verdict tier: {tier!r}") from None


@dataclass(frozen=True, slots=True)
class PolicyStore:
    version: int
    models: dict[str, ModelSpec]
    routing: dict[str, str]

    def verdict(self, model: str, profile: HardwareProfile) -> Verdict:
        """The raw PREFER/ALLOW/NEVER verdict for a model on a profile.

        Does not raise -- callers that want fail-closed behavior for an
        unknown model should use decide(), not this method directly.
        """
        spec = self.models.get(model)
        if spec is None:
            return "NEVER"
        return spec.verdict_for_tier(profile.verdict_tier)

    def decide(self, model: str, profile_id: str) -> Verdict:
        """The verdict for a model on a named profile, raising
        HardwareAffinityError on NEVER -- the behavior agate's own README
        documents as the contract for a forbidden model."""
        profile = get_profile(profile_id)
        verdict = self.verdict(model, profile)
        if verdict == "NEVER":
            spec = self.models.get(model)
            raise HardwareAffinityError(model, profile_id, notes=spec.notes if spec else "model not in policy")
        return verdict

    def preferred_model(self, profile_id: str, task_key: str = "default") -> str | None:
        """The routing table's model choice for a task key, verified
        against this profile -- returns None rather than a model this
        profile is actually forbidden from running."""
        profile = get_profile(profile_id)
        model = self.routing.get(task_key) or self.routing.get("default")
        if model is None:
            return None
        if self.verdict(model, profile) == "NEVER":
            return None
        return model


def _parse_model_spec(name: str, raw: dict) -> ModelSpec:
    def verdict_for(field: str) -> Verdict:
        verdict = raw.get(field, "NEVER")
        if verdict not in _VALID_VERDICTS:
            raise ValueError(
                f"invalid verdict for model {name!r}, tier {field!r}: {verdict!r}; "
                f"expected one of {sorted(_VALID_VERDICTS)}"
            )
        return verdict

    return ModelSpec(
        name=name,
        mac=verdict_for("mac"),
        windows=verdict_for("windows"),
        shared=verdict_for("shared"),
        context=raw.get("context"),
        roles=tuple(raw.get("roles", [])),
        notes=raw.get("notes"),
    )


def load_policy(path: Path | str | None = None) -> PolicyStore:
    """Load and parse a schema-conformant model_hardware_policy.yml.

    No caching here -- see load_policy_cached() for the process-wide
    cached accessor most callers should use instead.
    """
    if path is None:
        resource = resources.files("agate").joinpath(_DEFAULT_POLICY_RESOURCE)
        with resource.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    else:
        with Path(path).open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)

    if raw.get("version") != 1:
        raise ValueError(f"unsupported policy schema version: {raw.get('version')!r}")

    models = {
        name: _parse_model_spec(name, spec)
        for name, spec in raw.get("models", {}).items()
    }
    routing = dict(raw.get("routing", {}))

    for task_key, model_name in routing.items():
        if model_name not in models:
            raise ValueError(
                f"routing key {task_key!r} references unknown model {model_name!r}"
            )

    return PolicyStore(version=raw["version"], models=models, routing=routing)


@functools.lru_cache(maxsize=1)
def load_policy_cached() -> PolicyStore:
    """The default policy file, loaded once per process.

    Most callers want this rather than load_policy() directly. Tests
    that need a different file should call load_policy(path) explicitly
    instead of trying to invalidate this cache.
    """
    return load_policy()
