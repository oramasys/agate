"""agate -- hardware detection, selection, and model-fit authority.

First real implementation. Covers the part of the contract that was
already fully specified in the schema and README: loading a
model_hardware_policy.yml and answering PREFER/ALLOW/NEVER for a known
physical profile. Does not yet implement hardware detection (Phase-2
design work, not yet decided), the PROFILE_UNDERUSE reason code (exact
shape is an open decision for the repo owner), or machine-level
concurrency-safety enforcement (also an open scope decision) -- see
docs/mhs-local-metal-convergence.md and the synthesized migration plan
for what remains open.
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
    "HardwareAffinityError",
    "ModelSpec",
    "PolicyStore",
    "Verdict",
    "load_policy",
    "load_policy_cached",
    "MAC_STUDIO",
    "PROFILES",
    "WIN_RTX3080",
    "WIN_RTX5080",
    "HardwareProfile",
    "HardwareObservation",
    "ProfileStore",
    "get_profile",
    "identify_profile",
    "load_profile_store",
    "observe_local_hardware",
]

__version__ = "0.1.0"
