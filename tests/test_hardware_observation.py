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

    assert observed_command[0].lower().endswith("powershell.exe")
    assert observed_command[1:4] == [
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
SMI_PATH = "C:\\Windows\\System32\\nvidia-smi.exe"
RTX3080 = "NVIDIA GeForce RTX 3080"


def _windows_host(
    monkeypatch: pytest.MonkeyPatch,
    cim: dict[str, object],
    nvidia_smi: str | BaseException | None,
) -> None:
    """Mock a Windows host: ``cim`` is the PowerShell JSON, ``nvidia_smi`` its stdout.

    ``None`` means nvidia-smi is not installed; an exception instance is raised.
    """

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[0].endswith("powershell.exe"):
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(cim))
        if command[0] == SMI_PATH and nvidia_smi is not None:
            if isinstance(nvidia_smi, BaseException):
                raise nvidia_smi
            return subprocess.CompletedProcess(command, 0, stdout=nvidia_smi)
        raise FileNotFoundError(command[0])

    monkeypatch.setattr(profiles.platform, "system", lambda: "Windows")
    monkeypatch.setattr(profiles.platform, "processor", lambda: "fallback CPU")
    monkeypatch.setattr(profiles.subprocess, "run", fake_run)
    monkeypatch.setattr(
        profiles, "_nvidia_smi_path", lambda: SMI_PATH if nvidia_smi is not None else None
    )


_RTX3080_CIM: dict[str, object] = {
    "cpu": "12th Gen Intel(R) Core(TM) i9-12900K",
    "ram_gb": 32,
    "os_caption": "Microsoft Windows 11 Pro ",
    "accelerator": RTX3080,
    "registry_vram_bytes": None,
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
    _windows_host(
        monkeypatch,
        {**_RTX3080_CIM, "registry_vram_bytes": 16 * GIB},
        f"{RTX3080}, 10240\n",
    )
    assert profiles.observe_local_hardware().accelerator_memory_gb == 10


def test_nvidia_smi_16303_mib_rounds_to_16(monkeypatch: pytest.MonkeyPatch) -> None:
    _windows_host(monkeypatch, _RTX3080_CIM, f"{RTX3080}, 16303\n")
    assert profiles.observe_local_hardware().accelerator_memory_gb == 16


def test_vram_falls_back_to_registry_qword(monkeypatch: pytest.MonkeyPatch) -> None:
    _windows_host(monkeypatch, {**_RTX3080_CIM, "registry_vram_bytes": 10 * GIB}, None)
    assert profiles.observe_local_hardware().accelerator_memory_gb == 10


def test_nvidia_smi_not_used_for_non_nvidia_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    cim = {**_RTX3080_CIM, "accelerator": "Example GPU", "registry_vram_bytes": 8 * GIB}
    _windows_host(monkeypatch, cim, "Example GPU, 10240\n")
    assert profiles.observe_local_hardware().accelerator_memory_gb == 8


def test_adapter_ram_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    cim = {**_RTX3080_CIM, "adapter_ram_bytes": 2 * GIB}
    _windows_host(monkeypatch, cim, None)
    assert profiles.observe_local_hardware().accelerator_memory_gb is None


def test_multi_gpu_uses_the_matching_smi_row(monkeypatch: pytest.MonkeyPatch) -> None:
    smi = f"NVIDIA GeForce RTX 5080, 16303\n  {RTX3080.lower()} , 10240\n"
    _windows_host(monkeypatch, {**_RTX3080_CIM, "registry_vram_bytes": 10 * GIB}, smi)
    assert profiles.observe_local_hardware().accelerator_memory_gb == 10


def test_multi_gpu_without_matching_row_uses_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    smi = "NVIDIA GeForce RTX 5080, 16303\nNVIDIA GeForce RTX 4090, 24564\n"
    _windows_host(monkeypatch, {**_RTX3080_CIM, "registry_vram_bytes": 10 * GIB}, smi)
    assert profiles.observe_local_hardware().accelerator_memory_gb == 10


def test_multi_gpu_without_matching_row_or_registry_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _windows_host(monkeypatch, _RTX3080_CIM, "NVIDIA GeForce RTX 5080, 16303\n")
    assert profiles.observe_local_hardware().accelerator_memory_gb is None


def test_identical_cards_are_ambiguous_and_use_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    smi = f"{RTX3080}, 10240\n{RTX3080}, 10240\n"
    _windows_host(monkeypatch, {**_RTX3080_CIM, "registry_vram_bytes": 10 * GIB}, smi)
    assert profiles.observe_local_hardware().accelerator_memory_gb == 10
    _windows_host(monkeypatch, _RTX3080_CIM, smi)
    assert profiles.observe_local_hardware().accelerator_memory_gb is None


@pytest.mark.parametrize(
    "smi",
    [
        "",
        "garbage\n",
        f"{RTX3080}, 0\n",
        f"{RTX3080}, 99999999999999999999\n",
        f"{RTX3080}, 1048577\n",
        subprocess.TimeoutExpired("nvidia-smi", 10),
        UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"),
    ],
)
def test_unusable_nvidia_smi_falls_back_to_registry(
    monkeypatch: pytest.MonkeyPatch, smi: str | BaseException
) -> None:
    _windows_host(monkeypatch, {**_RTX3080_CIM, "registry_vram_bytes": 10 * GIB}, smi)
    assert profiles.observe_local_hardware().accelerator_memory_gb == 10
    _windows_host(monkeypatch, _RTX3080_CIM, smi)
    assert profiles.observe_local_hardware().accelerator_memory_gb is None


@pytest.mark.parametrize("registry", [2**70, 0, -5, 1025 * GIB])
def test_implausible_registry_vram_is_rejected(
    monkeypatch: pytest.MonkeyPatch, registry: int
) -> None:
    _windows_host(monkeypatch, {**_RTX3080_CIM, "registry_vram_bytes": registry}, None)
    assert profiles.observe_local_hardware().accelerator_memory_gb is None


def test_executables_are_resolved_to_absolute_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SystemRoot", "C:\\Windows")
    monkeypatch.setenv("ProgramFiles", "C:\\Program Files")
    seen: list[str] = []

    def fake_isfile(path: str) -> bool:
        seen.append(path)
        return path.endswith("NVSMI\\nvidia-smi.exe")

    monkeypatch.setattr(profiles.os.path, "isfile", fake_isfile)
    assert profiles._powershell_path() == (
        "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"
    )
    assert profiles._nvidia_smi_path() == (
        "C:\\Program Files\\NVIDIA Corporation\\NVSMI\\nvidia-smi.exe"
    )
    assert seen[0] == "C:\\Windows\\System32\\nvidia-smi.exe"
    assert all(profiles.ntpath.isabs(path) for path in seen)
    monkeypatch.setattr(profiles.os.path, "isfile", lambda _path: False)
    assert profiles._nvidia_smi_path() is None


def test_real_host_facts_identify_win_rtx3080(monkeypatch: pytest.MonkeyPatch) -> None:
    _windows_host(monkeypatch, _RTX3080_CIM, f"{RTX3080}, 10240\n")
    observation = profiles.observe_local_hardware()
    profile = profiles.identify_profile(observation)
    assert profile is not None and profile.profile_id == "win-rtx3080"


def test_unknown_vram_keeps_profile_unidentified(monkeypatch: pytest.MonkeyPatch) -> None:
    _windows_host(monkeypatch, _RTX3080_CIM, None)
    observation = profiles.observe_local_hardware()
    assert observation.os == "Windows 11 Pro"
    assert profiles.identify_profile(observation) is None


def test_windows_command_tolerates_protected_registry_subkeys_and_requires_agreement() -> None:
    """The registry scan must not abort on a protected subkey and must need one agreed value.

    On a real Windows 11 host, enumerating the display-adapter class key with
    ``-ErrorAction Stop`` throws ``SecurityException`` on a protected subkey, which made the
    registry fallback always return null. Same-name adapters reporting different sizes must
    leave VRAM unknown rather than borrowing another card's capacity.
    """
    from agate import profiles

    command = profiles._WINDOWS_HARDWARE_COMMAND
    assert "Get-ChildItem -LiteralPath $class -ErrorAction SilentlyContinue" in command
    assert "-ErrorAction Stop" not in command
    assert "Sort-Object -Unique" in command and "$distinct.Count -eq 1" in command
