"""Loader/schema parity tests for the portable hardware-profile database.

The authority is ``schemas/hardware_profiles.schema.json`` (Draft 2020-12);
``agate.load_profile_store()`` is one enforcement of it. These tests pin the
two together: every fixture in the corpus below must be accepted or rejected
by both, so the schema and the Python loader can never silently drift.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from agate import load_profile_store

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schemas" / "hardware_profiles.schema.json"
BINDING_SCHEMA_PATH = (
    REPO_ROOT / "bindings" / "typescript" / "schemas" / "hardware_profiles.schema.json"
)
REAL_DATABASE_PATH = REPO_ROOT / "src" / "agate" / "data" / "hardware_profiles.json"

SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
REAL_DATABASE = json.loads(REAL_DATABASE_PATH.read_text(encoding="utf-8"))

VALID_PROFILE: dict[str, Any] = {
    "profile_id": "test-profile",
    "role": "test machine",
    "verdict_tier": "mac",
    "os": "macOS",
    "cpu": "Apple M2 Pro",
    "ram_gb": 16,
    "accelerator": "Apple Silicon unified memory",
    "accelerator_memory_gb": 16,
    "match": {"os": "macOS", "cpu_contains": "M2 Pro", "ram_gb": 16},
}


def database_with(profile: dict[str, Any]) -> dict[str, Any]:
    return {"version": 1, "profiles": [profile]}


def schema_accepts(database: Any) -> bool:
    try:
        jsonschema.validate(database, SCHEMA)
    except jsonschema.ValidationError:
        return False
    return True


def loader_accepts(database: Any, tmp_path: Path) -> bool:
    path = tmp_path / "database.json"
    path.write_text(json.dumps(database), encoding="utf-8")
    try:
        load_profile_store(path)
    except ValueError:
        return False
    return True


def test_real_profile_database_validates_against_the_real_schema() -> None:
    """The packaged default database must stay schema-conformant as it is edited."""
    jsonschema.Draft202012Validator.check_schema(SCHEMA)
    jsonschema.validate(REAL_DATABASE, SCHEMA)
    load_profile_store(REAL_DATABASE_PATH)


def test_typescript_schema_projection_matches_the_canonical_schema() -> None:
    """The package asset must stay byte-for-byte aligned with the authority."""
    assert BINDING_SCHEMA_PATH.read_bytes() == SCHEMA_PATH.read_bytes()


# (label, mutate) pairs: mutate receives a deep copy of VALID_PROFILE and
# distorts it. "invalid" fixtures must be rejected by BOTH the schema and the
# loader; "valid" fixtures must be accepted by BOTH.
CORPUS: list[tuple[str, bool, Any]] = [
    ("baseline valid profile", True, lambda p: None),
    ("valid profile with every match field", True, lambda p: p.update({
        "match": {
            "os": "macOS",
            "cpu_contains": "M2 Pro",
            "accelerator_contains": "Apple",
            "ram_gb": 16,
            "accelerator_memory_gb": 16,
        },
        "notes": ["a note"],
    })),
    ("empty match object", False, lambda p: p.update(match={})),
    ("unsupported match key", False, lambda p: p.update(match={"os_name": "macOS"})),
    ("empty string predicate", False, lambda p: p.update(match={"os": ""})),
    ("whitespace-only predicate", False, lambda p: p.update(match={"cpu_contains": "   "})),
    ("non-string predicate", False, lambda p: p.update(match={"os": 1})),
    ("negative match ram_gb", False, lambda p: p.update(match={"ram_gb": -16})),
    ("zero match ram_gb", False, lambda p: p.update(match={"ram_gb": 0})),
    ("fractional match ram_gb", False, lambda p: p.update(match={"ram_gb": 16.5})),
    ("string match ram_gb", False, lambda p: p.update(match={"ram_gb": "16"})),
    ("boolean match ram_gb", False, lambda p: p.update(match={"ram_gb": True})),
    ("negative match accelerator_memory_gb", False, lambda p: p.update(match={"accelerator_memory_gb": -1})),
    ("boolean match accelerator_memory_gb", False, lambda p: p.update(match={"accelerator_memory_gb": False})),
    ("verdict tier outside vocabulary", False, lambda p: p.update(verdict_tier="linux")),
    ("verdict tier case mismatch", False, lambda p: p.update(verdict_tier="Mac")),
    ("verdict tier array", False, lambda p: p.update(verdict_tier=["mac"])),
    ("verdict tier object", False, lambda p: p.update(verdict_tier={"tier": "mac"})),
    ("missing required field", False, lambda p: p.pop("ram_gb")),
    ("empty profile_id", False, lambda p: p.update(profile_id="")),
    ("whitespace-only cpu", False, lambda p: p.update(cpu="  ")),
    ("non-string os", False, lambda p: p.update(os=11)),
    ("negative top-level ram_gb", False, lambda p: p.update(ram_gb=-16)),
    ("zero top-level ram_gb", False, lambda p: p.update(ram_gb=0)),
    ("fractional top-level ram_gb", False, lambda p: p.update(ram_gb=15.5)),
    ("string top-level ram_gb", False, lambda p: p.update(ram_gb="16")),
    ("boolean top-level ram_gb", False, lambda p: p.update(ram_gb=True)),
    ("negative top-level accelerator_memory_gb", False, lambda p: p.update(accelerator_memory_gb=-16)),
    ("string top-level accelerator_memory_gb", False, lambda p: p.update(accelerator_memory_gb="16")),
    ("unsupported top-level field", False, lambda p: p.update(unexpected=1)),
    ("notes not a list", False, lambda p: p.update(notes="a single note")),
    ("empty note entry", False, lambda p: p.update(notes=[""])),
    ("non-string note entry", False, lambda p: p.update(notes=[1])),
]


@pytest.mark.parametrize(
    "label,expected_valid,mutate",
    CORPUS,
    ids=[label for label, _, _ in CORPUS],
)
def test_loader_and_schema_parity(
    label: str, expected_valid: bool, mutate: Any, tmp_path: Path
) -> None:
    profile = copy.deepcopy(VALID_PROFILE)
    mutate(profile)
    database = database_with(profile)

    assert schema_accepts(database) is expected_valid, (
        f"schema disagreement on fixture {label!r}"
    )
    assert loader_accepts(database, tmp_path) is expected_valid, (
        f"loader disagreement on fixture {label!r}"
    )


@pytest.mark.parametrize(
    "database",
    [
        {"version": 2, "profiles": [VALID_PROFILE]},
        {"profiles": [VALID_PROFILE]},
        {"version": 1, "profiles": []},
        {"version": 1, "profiles": [VALID_PROFILE], "extra": 1},
        {"version": 1, "profiles": {}},
        {"version": True, "profiles": [VALID_PROFILE]},  # boolean is not an integer in JSON Schema
        {"version": 1, "profiles": [5]},
        {"version": 1, "profiles": [[]]},
        {"version": 1, "profiles": ["not an object"]},
        [],  # envelope itself is not an object
        42,
    ],
    ids=[
        "version-2",
        "missing-version",
        "empty-profiles",
        "extra-top-level-key",
        "profiles-not-array",
        "version-boolean",
        "profile-item-integer",
        "profile-item-array",
        "profile-item-string",
        "envelope-array",
        "envelope-integer",
    ],
)
def test_loader_and_schema_parity_on_database_envelope(
    database: Any, tmp_path: Path
) -> None:
    assert schema_accepts(database) is False
    assert loader_accepts(database, tmp_path) is False


def test_loader_enforces_unique_profile_ids(tmp_path: Path) -> None:
    """Uniqueness of profile_id is loader-enforced; it is not expressible
    in JSON Schema, so this is a loader-only guarantee, tested explicitly."""
    database = {
        "version": 1,
        "profiles": [VALID_PROFILE, copy.deepcopy(VALID_PROFILE)],
    }
    assert schema_accepts(database) is True
    path = tmp_path / "dup.json"
    path.write_text(json.dumps(database), encoding="utf-8")
    with pytest.raises(ValueError, match="uniquely named profiles"):
        load_profile_store(path)
