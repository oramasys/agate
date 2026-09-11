"""Agate's physical fleet profile registry.

These are the three canonical, proven fleet profiles this session's own
recall of PT's evidence (config/devices.yml, model-affinity tests, live
operational lessons) and the exact hardware specs supplied directly both
confirm. Not planned, not roadmap items -- each has direct operational
evidence: onboarding, loaded models, routing tests, live incidents.

Each profile maps to exactly one of agate's schema-level verdict tiers
(mac / windows / shared) for model-policy lookups, since the current
schema (schemas/model_hardware_policy.schema.json, v1) only supports
those three generic keys -- it has no notion of "win-rtx3080" vs
"win-rtx5080" as distinct verdict-bearing identities. That is a real,
known limitation, not silently worked around: PROFILES below keeps the
two Windows machines as distinct physical identities for capacity and
detection purposes, while model-policy verdicts (see policy.py) can only
be as granular as the v1 schema allows until a v2 schema decision is
made. Do not assume verdict-tier resolution distinguishes the two
Windows profiles -- it currently cannot.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class HardwareProfile:
    """A proven physical fleet profile."""

    profile_id: str
    role: str
    verdict_tier: str  # the schema-level key this profile resolves to: mac | windows | shared
    os: str
    cpu: str
    ram_gb: int
    accelerator: str
    accelerator_memory_gb: int
    notes: tuple[str, ...] = field(default_factory=tuple)


MAC_STUDIO = HardwareProfile(
    profile_id="mac-studio",
    role="Primary Orchestrator",
    verdict_tier="mac",
    os="macOS",
    cpu="Apple M2 Pro (10-core CPU, 16-core GPU)",
    ram_gb=16,
    accelerator="Apple Silicon unified memory",
    accelerator_memory_gb=16,
    notes=(
        "16 GB unified memory shared between CPU and GPU, not a separate VRAM pool.",
        "Preferred runtime: Ollama. MLX native lane available. LM Studio is "
        "mirror-only, excluded from dispatch (lesson_f60e9a3a7ade / "
        "lesson_0baf339c8840).",
        "CLOSED, NEVER-REOPEN safety constraint: never run Ollama and LM "
        "Studio under real concurrent heavy inference load on this machine "
        "-- confirmed prior overheat/force-shutdown incident "
        "(lesson_f60e9a3a7ade). Light-to-moderate single-request concurrency "
        "is a separate, narrower claim (lesson_fba170814ea7) and does not "
        "license heavy concurrent load.",
    ),
)

WIN_RTX3080 = HardwareProfile(
    profile_id="win-rtx3080",
    role="Windows AutoResearcher 1 / co-Orchestrator",
    verdict_tier="windows",
    os="Windows 11 Pro",
    cpu="Intel Core i9-12900",
    ram_gb=32,
    accelerator="NVIDIA GeForce RTX 3080 (Ampere, 8704 CUDA cores)",
    accelerator_memory_gb=10,
    notes=(
        "10 GB GDDR6X, 320-bit bus, 320 W -- confirmed against the real "
        "product spec sheet, resolving an earlier conflict between PT's "
        "config (10 GB, correct) and a v2 kernel-spec draft (24 GB, wrong).",
        "Preferred runtime: LM Studio, Ollama secondary.",
        "Endpoint identity must be live-resolved, never trusted from a "
        "cached or recently-written value -- DHCP IP drift confirmed "
        "directly (lesson_be16e0517158).",
    ),
)

WIN_RTX5080 = HardwareProfile(
    profile_id="win-rtx5080",
    role="Windows AutoResearcher 2 / co-Orchestrator",
    verdict_tier="windows",
    os="Windows 11 Pro",
    cpu="Intel Core Ultra 7 265KF (20C/20T, 3.9 GHz)",
    ram_gb=32,
    accelerator="NVIDIA GeForce RTX 5080 PRIME",
    accelerator_memory_gb=16,
    notes=(
        "Liquid-cooled, 1000 W Gold PSU.",
        "Preferred runtime: LM Studio.",
        "A distinct physical identity from win-rtx3080 -- both resolve to "
        "the same schema verdict_tier (windows) today, a known v1-schema "
        "limitation, not an intentional merging of their model fit.",
    ),
)

PROFILES: dict[str, HardwareProfile] = {
    p.profile_id: p for p in (MAC_STUDIO, WIN_RTX3080, WIN_RTX5080)
}


def get_profile(profile_id: str) -> HardwareProfile:
    try:
        return PROFILES[profile_id]
    except KeyError:
        raise KeyError(
            f"unknown hardware profile: {profile_id!r}. Known profiles: "
            f"{sorted(PROFILES)}"
        ) from None
