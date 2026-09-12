from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
import yaml

from agate import (
    HardwareObservation,
    MAC_STUDIO,
    WIN_RTX3080,
    WIN_RTX5080,
    HardwareAffinityError,
    get_profile,
    identify_profile,
    load_policy,
    load_profile_store,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_POLICY_PATH = REPO_ROOT / "config" / "model_hardware_policy.yml"
SCHEMA_PATH = REPO_ROOT / "schemas" / "model_hardware_policy.schema.json"
PACKAGED_POLICY_PATH = REPO_ROOT / "src" / "agate" / "data" / "model_hardware_policy.yml"


def test_real_policy_file_validates_against_the_real_schema() -> None:
    """Runs against the actual tracked files, not a synthetic fixture --
    the real seed data must stay schema-conformant as it's edited."""
    with open(SCHEMA_PATH) as f:
        schema = json.load(f)
    with open(REAL_POLICY_PATH) as f:
        data = yaml.safe_load(f)
    jsonschema.validate(data, schema)


def test_legacy_policy_path_is_a_relative_alias_of_the_packaged_default() -> None:
    assert REAL_POLICY_PATH.is_symlink()
    assert REAL_POLICY_PATH.readlink() == Path("../src/agate/data/model_hardware_policy.yml")
    assert REAL_POLICY_PATH.resolve() == PACKAGED_POLICY_PATH.resolve()


def test_real_policy_loads_and_matches_migrated_pt_data() -> None:
    """Confirms the real config file, migrated from PT's actual
    mac_only/windows_only/shared lists, loads correctly and preserves the
    known constraints -- not a synthetic fixture, the real tracked file."""
    store = load_policy(REAL_POLICY_PATH)

    # Mac-only models: PREFER on mac, NEVER everywhere else.
    assert store.verdict("qwen3.5:9b-nvfp4", MAC_STUDIO) == "PREFER"
    assert store.verdict("qwen3.5:9b-nvfp4", WIN_RTX3080) == "NEVER"
    assert store.verdict("bge-m3", MAC_STUDIO) == "PREFER"
    assert store.verdict("bge-m3", WIN_RTX3080) == "NEVER"

    # Windows-only models: NEVER on mac, PREFER on windows.
    assert store.verdict(
        "qwen3.5-27b-claude-4.6-opus-reasoning-distilled-v2", MAC_STUDIO
    ) == "NEVER"
    assert store.verdict(
        "qwen3.5-27b-claude-4.6-opus-reasoning-distilled-v2", WIN_RTX3080
    ) == "PREFER"
    # win-rtx5080 resolves to the same verdict_tier as win-rtx3080 today --
    # a known, documented schema limitation, not an oversight.
    assert store.verdict(
        "qwen3.5-27b-claude-4.6-opus-reasoning-distilled-v2", WIN_RTX5080
    ) == "PREFER"

    # Shared model with an asymmetric native/proxied relationship.
    assert store.verdict("qwen3.5-9b-mlx", MAC_STUDIO) == "PREFER"
    assert store.verdict("qwen3.5-9b-mlx", WIN_RTX3080) == "ALLOW"


def test_packaged_default_policy_loads_without_a_repository_relative_path() -> None:
    """Installed consumers must receive the default policy in the wheel."""
    store = load_policy()

    assert "qwen3.5:9b-nvfp4" in store.models


def test_decide_raises_hardware_affinity_error_on_never() -> None:
    """Matches agate's own README-documented contract for a NEVER verdict."""
    store = load_policy(REAL_POLICY_PATH)
    with pytest.raises(HardwareAffinityError) as exc_info:
        store.decide("qwen3.5:9b-nvfp4", "win-rtx3080")
    assert "qwen3.5:9b-nvfp4" in str(exc_info.value)
    assert "win-rtx3080" in str(exc_info.value)


def test_decide_returns_verdict_when_not_forbidden() -> None:
    store = load_policy(REAL_POLICY_PATH)
    assert store.decide("qwen3.5:9b-nvfp4", "mac-studio") == "PREFER"


def test_unknown_model_defaults_to_never_fail_closed() -> None:
    """A model not in the policy at all must fail closed (NEVER), not
    silently pass -- this is the fail-closed behavior the whole hardware-
    authority effort exists to guarantee."""
    store = load_policy(REAL_POLICY_PATH)
    assert store.verdict("totally-unknown-model-xyz", MAC_STUDIO) == "NEVER"
    with pytest.raises(HardwareAffinityError):
        store.decide("totally-unknown-model-xyz", "mac-studio")


def test_get_profile_raises_on_unknown_profile_id() -> None:
    with pytest.raises(KeyError, match="unknown hardware profile"):
        get_profile("not-a-real-machine")


def test_preferred_model_respects_forbidding_verdict() -> None:
    """preferred_model() must never return a model this profile is
    actually forbidden from running, even if the routing table names it
    as the default -- confirmed with a deliberately-conflicting fixture,
    not assumed from the real file's own consistency."""
    fixture = """
    version: 1
    models:
      mac-only-model:
        mac: PREFER
        windows: NEVER
        shared: NEVER
      fallback-model:
        mac: PREFER
        windows: ALLOW
        shared: PREFER
    routing:
      default: mac-only-model
    """
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(fixture)
        path = f.name

    store = load_policy(path)
    assert store.preferred_model("mac-studio") == "mac-only-model"
    assert store.preferred_model("win-rtx3080") is None

    Path(path).unlink()


def test_load_policy_rejects_unsupported_schema_version() -> None:
    import tempfile

    fixture = "version: 2\nmodels: {}\nrouting: {}\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(fixture)
        path = f.name

    with pytest.raises(ValueError, match="unsupported policy schema version"):
        load_policy(path)

    Path(path).unlink()


def test_load_policy_rejects_routing_referencing_unknown_model() -> None:
    import tempfile

    fixture = "version: 1\nmodels: {}\nrouting:\n  default: ghost-model\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(fixture)
        path = f.name

    with pytest.raises(ValueError, match="unknown model"):
        load_policy(path)

    Path(path).unlink()


@pytest.mark.parametrize("invalid_verdict", ["NEVRE", "prefer", 1])
def test_load_policy_rejects_invalid_verdicts(invalid_verdict: object, tmp_path: Path) -> None:
    path = tmp_path / "invalid.yml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "models": {"bad-model": {"mac": invalid_verdict}},
                "routing": {"default": "bad-model"},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid verdict"):
        load_policy(path)


def test_profile_database_is_plaintext_and_identifies_a_matching_observation() -> None:
    store = load_profile_store()
    profile = store.profiles["win-rtx3080"]
    observation = HardwareObservation(
        os="Windows 11 Pro",
        cpu="Intel Core i9-12900",
        ram_gb=32,
        accelerator="NVIDIA GeForce RTX 3080",
        accelerator_memory_gb=10,
    )

    assert identify_profile(observation) == profile


def test_the_three_profiles_have_correct_verdict_tier_mapping() -> None:
    """win-rtx3080 and win-rtx5080 are distinct physical identities but
    both resolve to the same schema verdict_tier today -- documented as a
    known limitation, tested here so a future schema-v2 migration has a
    clear regression point to update."""
    assert MAC_STUDIO.verdict_tier == "mac"
    assert WIN_RTX3080.verdict_tier == "windows"
    assert WIN_RTX5080.verdict_tier == "windows"
    assert WIN_RTX3080.profile_id != WIN_RTX5080.profile_id


@pytest.mark.parametrize(
    "match",
    [
        {},
        {"os_name": "Windows"},
        {"os": 1},
        {"cpu_contains": 1},
        {"ram_gb": "32"},
        {"accelerator_contains": []},
        {"accelerator_memory_gb": True},
    ],
)
def test_profile_database_rejects_invalid_match_schema(
    match: object, tmp_path: Path
) -> None:
    """No editable profile may match without validated hardware evidence."""
    path = tmp_path / "invalid-profile-database.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "profiles": [
                    {
                        "profile_id": "invalid",
                        "role": "test",
                        "verdict_tier": "mac",
                        "os": "macOS",
                        "cpu": "test",
                        "ram_gb": 1,
                        "accelerator": "test",
                        "accelerator_memory_gb": 1,
                        "match": match,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid hardware profile match"):
        load_profile_store(path)
