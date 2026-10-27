"""Best-effort hardware observation tests using synthetic local-command output."""
from __future__ import annotations

import json
import subprocess

import pytest

import agate.profiles as profiles


def test_windows_observer_reads_cim_json_without_claiming_a_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_command: list[str] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        observed_command.extend(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "cpu": "Example CPU",
                    "ram_gb": 32,
                    "accelerator": "Example GPU",
                    "registry_vram_bytes": 16 * 2**30,
                }
            ),
        )

    monkeypatch.setattr(profiles.platform, "system", lambda: "Windows")
    monkeypatch.setattr(profiles.platform, "processor", lambda: "fallback CPU")
    monkeypatch.setattr(profiles.subprocess, "run", fake_run)

    observation = profiles.observe_local_hardware()

    assert observed_command[:4] == [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
    ]
    assert observation == profiles.HardwareObservation(
        os="Windows",
        cpu="Example CPU",
        ram_gb=32,
        accelerator="Example GPU",
        accelerator_memory_gb=16,
    )


@pytest.mark.parametrize(
    "stdout",
    ["not-json", "[]", '{"cpu": " ", "ram_gb": 0, "accelerator_memory_gb": true}'],
)
def test_windows_observer_fails_closed_on_unusable_cim_output(
    monkeypatch: pytest.MonkeyPatch,
    stdout: str,
) -> None:
    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout=stdout)

    monkeypatch.setattr(profiles.platform, "system", lambda: "Windows")
    monkeypatch.setattr(profiles.platform, "processor", lambda: "fallback CPU")
    monkeypatch.setattr(profiles.subprocess, "run", fake_run)

    observation = profiles.observe_local_hardware()

    assert observation.os == "Windows"
    assert observation.cpu == "fallback CPU"
    assert observation.ram_gb is None
    assert observation.accelerator is None
    assert observation.accelerator_memory_gb is None


GIB = 2**30


def _windows_host(
    monkeypatch: pytest.MonkeyPatch,
    cim: dict[str, object],
    nvidia_smi: str | None,
) -> None:
    """Mock a Windows host: ``cim`` is the PowerShell JSON, ``nvidia_smi`` its stdout."""

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[0] == "powershell":
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(cim))
        if command[0] == "nvidia-smi" and nvidia_smi is not None:
            return subprocess.CompletedProcess(command, 0, stdout=nvidia_smi)
        raise FileNotFoundError(command[0])

    monkeypatch.setattr(profiles.platform, "system", lambda: "Windows")
    monkeypatch.setattr(profiles.platform, "processor", lambda: "fallback CPU")
    monkeypatch.setattr(profiles.subprocess, "run", fake_run)


_RTX3080_CIM: dict[str, object] = {
    "cpu": "12th Gen Intel(R) Core(TM) i9-12900K",
    "ram_gb": 32,
    "os_caption": "Microsoft Windows 11 Pro ",
    "accelerator": "NVIDIA GeForce RTX 3080",
    "registry_vram_bytes": None,
    "adapter_ram_bytes": 4294967295,
}


def test_windows_caption_is_normalised_to_edition(monkeypatch: pytest.MonkeyPatch) -> None:
    _windows_host(monkeypatch, _RTX3080_CIM, None)
    assert profiles.observe_local_hardware().os == "Windows 11 Pro"


@pytest.mark.parametrize("caption", [None, "", "  ", 7])
def test_windows_missing_caption_keeps_plain_windows(
    monkeypatch: pytest.MonkeyPatch, caption: object
) -> None:
    _windows_host(monkeypatch, {**_RTX3080_CIM, "os_caption": caption}, None)
    assert profiles.observe_local_hardware().os == "Windows"


def test_windows_vram_prefers_nvidia_smi(monkeypatch: pytest.MonkeyPatch) -> None:
    _windows_host(monkeypatch, {**_RTX3080_CIM, "registry_vram_bytes": 16 * GIB}, "10240\n")
    assert profiles.observe_local_hardware().accelerator_memory_gb == 10


def test_nvidia_smi_16303_mib_rounds_to_16(monkeypatch: pytest.MonkeyPatch) -> None:
    _windows_host(monkeypatch, _RTX3080_CIM, "16303\n")
    assert profiles.observe_local_hardware().accelerator_memory_gb == 16


def test_vram_falls_back_to_registry_qword(monkeypatch: pytest.MonkeyPatch) -> None:
    _windows_host(monkeypatch, {**_RTX3080_CIM, "registry_vram_bytes": 10 * GIB}, None)
    assert profiles.observe_local_hardware().accelerator_memory_gb == 10


def test_nvidia_smi_not_used_for_non_nvidia_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    cim = {**_RTX3080_CIM, "accelerator": "Example GPU", "registry_vram_bytes": 8 * GIB}
    _windows_host(monkeypatch, cim, "10240\n")
    assert profiles.observe_local_hardware().accelerator_memory_gb == 8


def test_capped_adapter_ram_is_never_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    _windows_host(monkeypatch, _RTX3080_CIM, None)
    assert profiles.observe_local_hardware().accelerator_memory_gb is None


def test_uncapped_adapter_ram_is_used_as_last_resort(monkeypatch: pytest.MonkeyPatch) -> None:
    _windows_host(monkeypatch, {**_RTX3080_CIM, "adapter_ram_bytes": 2 * GIB}, None)
    assert profiles.observe_local_hardware().accelerator_memory_gb == 2


@pytest.mark.parametrize("smi", ["", "garbage\n", "0\n"])
def test_unusable_nvidia_smi_output_degrades_to_none(
    monkeypatch: pytest.MonkeyPatch, smi: str
) -> None:
    _windows_host(monkeypatch, _RTX3080_CIM, smi)
    assert profiles.observe_local_hardware().accelerator_memory_gb is None


def test_real_host_facts_identify_win_rtx3080(monkeypatch: pytest.MonkeyPatch) -> None:
    _windows_host(monkeypatch, _RTX3080_CIM, "10240\n")
    observation = profiles.observe_local_hardware()
    profile = profiles.identify_profile(observation)
    assert profile is not None and profile.profile_id == "win-rtx3080"


def test_unknown_vram_keeps_profile_unidentified(monkeypatch: pytest.MonkeyPatch) -> None:
    _windows_host(monkeypatch, _RTX3080_CIM, None)
    observation = profiles.observe_local_hardware()
    assert observation.os == "Windows 11 Pro"
    assert profiles.identify_profile(observation) is None
