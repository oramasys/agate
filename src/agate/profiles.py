"""Portable hardware-profile data, observation, and identity matching.

Profile specifications are data, not Python constants. The package ships a
conservative default database and an operator can select an editable JSON file
with ``AGATE_PROFILE_DATABASE``. A live observation is evidence only: it is
matched against the database but never rewrites operator policy or profile data.
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class HardwareProfile:
    """A named physical profile loaded from the portable profile database."""

    profile_id: str
    role: str
    verdict_tier: str
    os: str
    cpu: str
    ram_gb: int
    accelerator: str
    accelerator_memory_gb: int
    notes: tuple[str, ...] = field(default_factory=tuple)
    match: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True, slots=True)
class HardwareObservation:
    """Best-effort locally observed hardware facts, kept distinct from policy."""

    os: str | None = None
    cpu: str | None = None
    ram_gb: int | None = None
    accelerator: str | None = None
    accelerator_memory_gb: int | None = None


@dataclass(frozen=True, slots=True)
class ProfileStore:
    version: int
    profiles: dict[str, HardwareProfile]


_DEFAULT_PROFILE_RESOURCE = "data/hardware_profiles.json"
_PROFILE_DATABASE_ENV = "AGATE_PROFILE_DATABASE"
_STRING_MATCH_FIELDS = {"os", "cpu_contains", "accelerator_contains"}
_INTEGER_MATCH_FIELDS = {"ram_gb", "accelerator_memory_gb"}
_MATCH_FIELDS = _STRING_MATCH_FIELDS | _INTEGER_MATCH_FIELDS
_WINDOWS_HARDWARE_COMMAND = (
    "$cpu = (Get-CimInstance Win32_Processor | Select-Object -First 1 "
    "-ExpandProperty Name); "
    "$system = Get-CimInstance Win32_ComputerSystem; "
    "$gpu = Get-CimInstance Win32_VideoController | Select-Object -First 1; "
    "[PSCustomObject]@{cpu=$cpu;ram_gb=[math]::Round($system.TotalPhysicalMemory "
    "/ 1GB);accelerator=$gpu.Name;accelerator_memory_gb=[math]::Round($gpu.AdapterRAM "
    "/ 1GB)} | ConvertTo-Json -Compress"
)


def _read_database(path: Path | str | None) -> Any:
    if path is not None:
        with Path(path).open(encoding="utf-8") as handle:
            return json.load(handle)

    override = os.environ.get(_PROFILE_DATABASE_ENV)
    if override:
        return _read_database(override)

    resource = resources.files("agate").joinpath(_DEFAULT_PROFILE_RESOURCE)
    with resource.open(encoding="utf-8") as handle:
        return json.load(handle)


def _is_valid_memory_gb(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 1


def _is_valid_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _observed_positive_integer(value: object) -> int | None:
    """Return a whole positive observed capacity without coercing strings/bools."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 1:
        return value
    if isinstance(value, float) and value.is_integer() and value >= 1:
        return int(value)
    return None


def _observe_windows_hardware(fallback_cpu: str | None) -> HardwareObservation:
    """Collect local Windows hardware facts through CIM without network I/O."""
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                _WINDOWS_HARDWARE_COMMAND,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        data = json.loads(result.stdout)
    except (
        OSError,
        subprocess.SubprocessError,
        ValueError,
        json.JSONDecodeError,
        TypeError,
    ):
        return HardwareObservation(os="Windows", cpu=fallback_cpu)

    if not isinstance(data, dict):
        return HardwareObservation(os="Windows", cpu=fallback_cpu)

    cpu = data.get("cpu")
    accelerator = data.get("accelerator")
    return HardwareObservation(
        os="Windows",
        cpu=cpu if _is_valid_text(cpu) else fallback_cpu,
        ram_gb=_observed_positive_integer(data.get("ram_gb")),
        accelerator=accelerator if _is_valid_text(accelerator) else None,
        accelerator_memory_gb=_observed_positive_integer(
            data.get("accelerator_memory_gb")
        ),
    )


def _parse_profile(raw: dict[str, Any]) -> HardwareProfile:
    # Keep in parity with schemas/hardware_profiles.schema.json (Draft 2020-12):
    # the schema is the contract, this loader is one enforcement of it, and
    # tests assert both accept and reject the same corpus.
    if not isinstance(raw, dict):
        raise ValueError("hardware profile must be an object")
    required = {
        "profile_id", "role", "verdict_tier", "os", "cpu", "ram_gb",
        "accelerator", "accelerator_memory_gb", "match",
    }
    missing = required - raw.keys()
    if missing:
        raise ValueError(f"hardware profile missing required fields: {sorted(missing)}")
    if raw.keys() - required - {"notes"}:
        raise ValueError(f"hardware profile has unsupported fields: {sorted(raw.keys() - required - {'notes'})}")
    for field_name in ("profile_id", "role", "os", "cpu", "accelerator"):
        if not _is_valid_text(raw[field_name]):
            raise ValueError(f"invalid hardware profile field: {field_name}")
    if (
        not isinstance(raw["verdict_tier"], str)
        or raw["verdict_tier"] not in {"mac", "windows", "shared"}
    ):
        raise ValueError(f"invalid verdict tier: {raw['verdict_tier']!r}")
    for field_name in ("ram_gb", "accelerator_memory_gb"):
        if not _is_valid_memory_gb(raw[field_name]):
            raise ValueError(f"invalid hardware profile memory value: {field_name}")
    notes = raw.get("notes", [])
    if not isinstance(notes, list) or any(not _is_valid_text(note) for note in notes):
        raise ValueError("invalid hardware profile notes")
    if not isinstance(raw["match"], dict):
        raise ValueError("hardware profile match must be an object")
    match = raw["match"]
    if not match or match.keys() - _MATCH_FIELDS:
        raise ValueError("invalid hardware profile match constraints")
    for field_name in _STRING_MATCH_FIELDS:
        if field_name in match and not _is_valid_text(match[field_name]):
            raise ValueError(f"invalid hardware profile match value: {field_name}")
    for field_name in _INTEGER_MATCH_FIELDS:
        if field_name in match and not _is_valid_memory_gb(match[field_name]):
            raise ValueError(f"invalid hardware profile match value: {field_name}")
    return HardwareProfile(
        profile_id=raw["profile_id"], role=raw["role"],
        verdict_tier=raw["verdict_tier"], os=raw["os"],
        cpu=raw["cpu"], ram_gb=raw["ram_gb"],
        accelerator=raw["accelerator"],
        accelerator_memory_gb=raw["accelerator_memory_gb"],
        notes=tuple(notes),
        match=dict(match),
    )


def load_profile_store(path: Path | str | None = None) -> ProfileStore:
    """Load an editable portable profile database or the package default."""
    raw = _read_database(path)
    if not isinstance(raw, dict):
        raise ValueError("profile database must be a JSON object")
    if raw.keys() - {"version", "profiles"}:
        raise ValueError(f"profile database has unsupported fields: {sorted(raw.keys() - {'version', 'profiles'})}")
    version = raw.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version != 1:
        raise ValueError(f"unsupported profile database version: {raw.get('version')!r}")
    raw_profiles = raw.get("profiles")
    if not isinstance(raw_profiles, list):
        raise ValueError("profile database profiles must be an array")
    profiles = [_parse_profile(item) for item in raw_profiles]
    by_id = {profile.profile_id: profile for profile in profiles}
    if not by_id or len(by_id) != len(profiles):
        raise ValueError("profile database must contain uniquely named profiles")
    return ProfileStore(version=1, profiles=by_id)


def get_profile(profile_id: str, path: Path | str | None = None) -> HardwareProfile:
    profiles = load_profile_store(path).profiles
    try:
        return profiles[profile_id]
    except KeyError:
        raise KeyError(
            f"unknown hardware profile: {profile_id!r}. Known profiles: {sorted(profiles)}"
        ) from None


def _contains(observed: str | None, expected: object) -> bool:
    return observed is not None and str(expected).casefold() in observed.casefold()


def _matches(profile: HardwareProfile, observation: HardwareObservation) -> bool:
    match = profile.match
    if "os" in match and observation.os != match["os"]:
        return False
    if "cpu_contains" in match and not _contains(observation.cpu, match["cpu_contains"]):
        return False
    if "ram_gb" in match and observation.ram_gb != match["ram_gb"]:
        return False
    if "accelerator_contains" in match and not _contains(observation.accelerator, match["accelerator_contains"]):
        return False
    if "accelerator_memory_gb" in match and observation.accelerator_memory_gb != match["accelerator_memory_gb"]:
        return False
    return True


def identify_profile(observation: HardwareObservation, path: Path | str | None = None) -> HardwareProfile | None:
    """Return one verified profile, or ``None`` when evidence is incomplete."""
    matches = [profile for profile in load_profile_store(path).profiles.values() if _matches(profile, observation)]
    if len(matches) > 1:
        raise ValueError(f"hardware observation matches multiple profiles: {[p.profile_id for p in matches]}")
    return matches[0] if matches else None


def observe_local_hardware() -> HardwareObservation:
    """Collect best-effort local facts without network or provider I/O.

    A failed platform collector leaves evidence incomplete; it never claims a
    profile. Python/shell callers can instead supply a maintained JSON database.
    """
    system = platform.system()
    os_name = {"Darwin": "macOS", "Windows": "Windows"}.get(system, system or None)
    cpu = platform.processor() or platform.machine() or None
    if system == "Windows":
        return _observe_windows_hardware(cpu)

    try:
        ram_gb = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30)
    except (AttributeError, OSError, ValueError):
        ram_gb = None
    accelerator: str | None = None
    accelerator_memory_gb: int | None = None

    if system == "Darwin":
        try:
            result = subprocess.run(
                ["system_profiler", "SPHardwareDataType", "SPDisplaysDataType", "-json"],
                check=True, capture_output=True, text=True, timeout=10,
            )
            data = json.loads(result.stdout)
            hardware = data.get("SPHardwareDataType", [{}])[0]
            displays = data.get("SPDisplaysDataType", [{}])
            cpu = hardware.get("chip_type") or hardware.get("cpu_type") or cpu
            accelerator = displays[0].get("sppci_model") if displays else None
            memory = displays[0].get("spdisplays_vram") if displays else None
            if isinstance(memory, str):
                digits = "".join(char for char in memory if char.isdigit())
                accelerator_memory_gb = int(digits) if digits else None
        except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError, KeyError):
            pass

    return HardwareObservation(os_name, cpu, ram_gb, accelerator, accelerator_memory_gb)


# Compatibility exports remain data-derived. Runtime decisions use get_profile(),
# so an operator-selected database is consulted at decision time.
_DEFAULT_PROFILES = load_profile_store().profiles
MAC_STUDIO = _DEFAULT_PROFILES["mac-studio"]
WIN_RTX3080 = _DEFAULT_PROFILES["win-rtx3080"]
WIN_RTX5080 = _DEFAULT_PROFILES["win-rtx5080"]
PROFILES = _DEFAULT_PROFILES
