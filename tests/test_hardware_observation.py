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
                    "accelerator_memory_gb": 16,
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
