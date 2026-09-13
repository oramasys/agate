"""agate -- hardware detection, selection, and model-fit authority.

First real implementation. Covers the part of the contract that was
already fully specified in the schema and README: loading a
model_hardware_policy.yml, collecting best-effort local observations on macOS
and Windows, and answering PREFER/ALLOW/NEVER for a known physical profile.
Observation never rewrites policy or proves a host profile by itself. The
PROFILE_UNDERUSE reason code (exact shape is an open decision for the repo
owner) and machine-level concurrency-safety enforcement remain deferred -- see
docs/mhs-local-metal-convergence.md and the synthesized migration plan.
"""
from .policy import (
    HardwareAffinityError,
    ModelSpec,
    PolicyStore,
    Verdict,
    load_policy,
    load_policy_cached,
)
from .profiles import (
    HardwareObservation,
    MAC_STUDIO,
    PROFILES,
    WIN_RTX3080,
    WIN_RTX5080,
    HardwareProfile,
    ProfileStore,
    get_profile,
    identify_profile,
    load_profile_store,
    observe_local_hardware,
)

__all__ = [
    "MAC_STUDIO",
    "PROFILES",
    "WIN_RTX3080",
    "WIN_RTX5080",
    "HardwareAffinityError",
    "HardwareObservation",
    "HardwareProfile",
    "ModelSpec",
    "PolicyStore",
    "ProfileStore",
    "Verdict",
    "get_profile",
    "identify_profile",
    "load_policy",
    "load_policy_cached",
    "load_profile_store",
    "observe_local_hardware",
]

__version__ = "1.9.0"
