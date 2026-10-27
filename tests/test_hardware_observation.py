"""Best-effort hardware observation tests using synthetic local-command output."""
from __future__ import annotations

import json
import subprocess

import pytest

import agate.profiles as profiles


def test_windows_observer_reads_cim_json_without_claiming_a_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Check: windows observer reads cim json without claiming a profile."""
    observed_command: list[str] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        """Test double: fake run."""
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
    """Check: windows observer fails closed on unusable cim output."""
    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        """Test double: fake run."""
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
        """Test double: fake run."""
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
    """Check: windows caption is normalised to edition."""
    _windows_host(monkeypatch, _RTX3080_CIM, None)
    assert profiles.observe_local_hardware().os == "Windows 11 Pro"


@pytest.mark.parametrize("caption", [None, "", "  ", 7])
def test_windows_missing_caption_keeps_plain_windows(
    monkeypatch: pytest.MonkeyPatch, caption: object
) -> None:
    """Check: windows missing caption keeps plain windows."""
    _windows_host(monkeypatch, {**_RTX3080_CIM, "os_caption": caption}, None)
    assert profiles.observe_local_hardware().os == "Windows"


def test_windows_vram_prefers_nvidia_smi(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check: windows vram prefers nvidia smi."""
    _windows_host(
        monkeypatch,
        {**_RTX3080_CIM, "registry_vram_bytes": 16 * GIB},
        f"{RTX3080}, 10240\n",
    )
    assert profiles.observe_local_hardware().accelerator_memory_gb == 10


def test_nvidia_smi_16303_mib_rounds_to_16(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check: nvidia smi 16303 mib rounds to 16."""
    _windows_host(monkeypatch, _RTX3080_CIM, f"{RTX3080}, 16303\n")
    assert profiles.observe_local_hardware().accelerator_memory_gb == 16


def test_vram_falls_back_to_registry_qword(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check: vram falls back to registry qword."""
    _windows_host(monkeypatch, {**_RTX3080_CIM, "registry_vram_bytes": 10 * GIB}, None)
    assert profiles.observe_local_hardware().accelerator_memory_gb == 10


def test_nvidia_smi_not_used_for_non_nvidia_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check: nvidia smi not used for non nvidia adapter."""
    cim = {**_RTX3080_CIM, "accelerator": "Example GPU", "registry_vram_bytes": 8 * GIB}
    _windows_host(monkeypatch, cim, "Example GPU, 10240\n")
    assert profiles.observe_local_hardware().accelerator_memory_gb == 8


def test_adapter_ram_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check: adapter ram is ignored."""
    cim = {**_RTX3080_CIM, "adapter_ram_bytes": 2 * GIB}
    _windows_host(monkeypatch, cim, None)
    assert profiles.observe_local_hardware().accelerator_memory_gb is None


def test_multi_gpu_uses_the_matching_smi_row(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check: multi gpu uses the matching smi row."""
    smi = f"NVIDIA GeForce RTX 5080, 16303\n  {RTX3080.lower()} , 10240\n"
    _windows_host(monkeypatch, {**_RTX3080_CIM, "registry_vram_bytes": 10 * GIB}, smi)
    assert profiles.observe_local_hardware().accelerator_memory_gb == 10


def test_multi_gpu_without_matching_row_uses_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check: multi gpu without matching row uses registry."""
    smi = "NVIDIA GeForce RTX 5080, 16303\nNVIDIA GeForce RTX 4090, 24564\n"
    _windows_host(monkeypatch, {**_RTX3080_CIM, "registry_vram_bytes": 10 * GIB}, smi)
    assert profiles.observe_local_hardware().accelerator_memory_gb == 10


def test_multi_gpu_without_matching_row_or_registry_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Check: multi gpu without matching row or registry is none."""
    _windows_host(monkeypatch, _RTX3080_CIM, "NVIDIA GeForce RTX 5080, 16303\n")
    assert profiles.observe_local_hardware().accelerator_memory_gb is None


def test_identical_cards_are_ambiguous_and_use_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Check: identical cards are ambiguous and use registry."""
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
        subprocess.CalledProcessError(9, "nvidia-smi", stderr="NVIDIA-SMI has failed"),
        FileNotFoundError("nvidia-smi.exe"),
        PermissionError("access denied"),
    ],
)
def test_unusable_nvidia_smi_falls_back_to_registry(
    monkeypatch: pytest.MonkeyPatch, smi: str | BaseException
) -> None:
    """Bad output or any run failure (non-zero exit, vanished binary, EACCES, timeout,
    undecodable bytes) uses the registry VRAM, or None when the registry has none."""
    _windows_host(monkeypatch, {**_RTX3080_CIM, "registry_vram_bytes": 10 * GIB}, smi)
    assert profiles.observe_local_hardware().accelerator_memory_gb == 10
    _windows_host(monkeypatch, _RTX3080_CIM, smi)
    assert profiles.observe_local_hardware().accelerator_memory_gb is None


@pytest.mark.parametrize("registry", [2**70, 0, -5, 1025 * GIB])
def test_implausible_registry_vram_is_rejected(
    monkeypatch: pytest.MonkeyPatch, registry: int
) -> None:
    """Check: implausible registry vram is rejected."""
    _windows_host(monkeypatch, {**_RTX3080_CIM, "registry_vram_bytes": registry}, None)
    assert profiles.observe_local_hardware().accelerator_memory_gb is None


def test_executables_are_resolved_to_absolute_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Check: executables are resolved to absolute paths."""
    monkeypatch.setenv("SystemRoot", "C:\\Windows")
    monkeypatch.setenv("ProgramFiles", "C:\\Program Files")
    seen: list[str] = []

    def fake_isfile(path: str) -> bool:
        """Test double: fake isfile."""
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
    """Check: real host facts identify win rtx3080."""
    _windows_host(monkeypatch, _RTX3080_CIM, f"{RTX3080}, 10240\n")
    observation = profiles.observe_local_hardware()
    profile = profiles.identify_profile(observation)
    assert profile is not None and profile.profile_id == "win-rtx3080"


def test_unknown_vram_keeps_profile_unidentified(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check: unknown vram keeps profile unidentified."""
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


def _mac_host(
    monkeypatch: pytest.MonkeyPatch,
    profiler: dict[str, object] | BaseException,
    ram_gb: int | None = 16,
) -> list[dict[str, object]]:
    """Mock a macOS host; returns the kwargs of each ``system_profiler`` call."""
    calls: list[dict[str, object]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        """Test double: fake run."""
        calls.append(kwargs)
        if isinstance(profiler, BaseException):
            raise profiler
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(profiler))

    monkeypatch.setattr(profiles.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(profiles.platform, "processor", lambda: "arm")
    monkeypatch.setattr(profiles.subprocess, "run", fake_run)
    if ram_gb is None:
        def no_sysconf(_name: str) -> int:
            """Test double: no sysconf."""
            raise ValueError("unavailable")

        monkeypatch.setattr(profiles.os, "sysconf", no_sysconf, raising=False)
    else:
        monkeypatch.setattr(
            profiles.os, "sysconf",
            lambda name: 4096 if name == "SC_PAGE_SIZE" else ram_gb * 2**30 // 4096,
            raising=False,
        )
    return calls


def _apple_silicon(**display: object) -> dict[str, object]:
    """Test double: apple silicon."""
    return {
        "SPHardwareDataType": [{"chip_type": "Apple M2 Pro"}],
        "SPDisplaysDataType": [{"sppci_model": "Apple M2 Pro", **display}],
    }


def test_apple_silicon_unified_memory_identifies_mac_studio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Check: apple silicon unified memory identifies mac studio."""
    calls = _mac_host(monkeypatch, _apple_silicon(sppci_bus="spdisplays_builtin"))
    observation = profiles.observe_local_hardware()
    assert calls[0]["timeout"] == 30
    assert (observation.os, observation.ram_gb) == ("macOS", 16)
    assert observation.accelerator_memory_gb == 16
    profile = profiles.identify_profile(observation)
    assert profile is not None and profile.profile_id == "mac-studio"


def test_apple_silicon_without_builtin_bus_still_maps(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check: apple silicon without builtin bus still maps."""
    _mac_host(monkeypatch, _apple_silicon())
    assert profiles.observe_local_hardware().accelerator_memory_gb == 16


def test_intel_mac_keeps_spdisplays_vram(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check: intel mac keeps spdisplays vram."""
    _mac_host(monkeypatch, {
        "SPHardwareDataType": [{"cpu_type": "Intel Core i9"}],
        "SPDisplaysDataType": [{"sppci_model": "AMD Radeon Pro", "spdisplays_vram": "8 GB"}],
    })
    assert profiles.observe_local_hardware().accelerator_memory_gb == 8


def test_apple_chip_with_non_apple_gpu_gets_no_unified_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Check: apple chip with non apple gpu gets no unified mapping."""
    data = _apple_silicon()
    data["SPDisplaysDataType"] = [{"sppci_model": "AMD Radeon RX"}]
    _mac_host(monkeypatch, data)
    assert profiles.observe_local_hardware().accelerator_memory_gb is None


def test_unknown_ram_leaves_unified_memory_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check: unknown ram leaves unified memory none."""
    _mac_host(monkeypatch, _apple_silicon(), ram_gb=None)
    observation = profiles.observe_local_hardware()
    assert observation.accelerator_memory_gb is None
    assert profiles.identify_profile(observation) is None


def test_system_profiler_timeout_reports_nothing_half_observed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Check: system profiler timeout reports nothing half observed."""
    calls = _mac_host(monkeypatch, subprocess.TimeoutExpired("system_profiler", 30))
    observation = profiles.observe_local_hardware()
    assert calls[0]["timeout"] == 30
    assert observation.cpu is None and observation.accelerator is None
    assert observation.accelerator_memory_gb is None
    assert profiles.identify_profile(observation) is None


def _displays(*models: str) -> dict[str, object]:
    """Test double: displays."""
    return {
        "SPHardwareDataType": [{"chip_type": "Apple M2 Pro"}],
        "SPDisplaysDataType": [{"sppci_model": m} if m else {"_name": "x"} for m in models],
    }


def test_apple_gpu_with_egpu_gets_no_unified_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check: apple gpu with egpu gets no unified mapping."""
    _mac_host(monkeypatch, _displays("Apple M2 Pro", "AMD Radeon RX"))
    observation = profiles.observe_local_hardware()
    assert observation.accelerator_memory_gb is None
    assert profiles.identify_profile(observation) is None


def test_egpu_first_then_apple_gets_no_unified_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check: egpu first then apple gets no unified mapping."""
    _mac_host(monkeypatch, _displays("AMD Radeon RX", "Apple M2 Pro"))
    assert profiles.observe_local_hardware().accelerator_memory_gb is None


def test_entries_without_model_are_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check: entries without model are skipped."""
    _mac_host(monkeypatch, _displays("", "Apple M2 Pro"))
    observation = profiles.observe_local_hardware()
    assert observation.accelerator == "Apple M2 Pro"
    profile = profiles.identify_profile(observation)
    assert profile is not None and profile.profile_id == "mac-studio"


@pytest.mark.parametrize(
    ("text", "expected"),
    [("1536 MB", 2), ("8 GB", 8), ("1 TB", 1024), ("Dynamic, Max", None),
     ("8 PB", None), ("0 GB", None), ("2 TB", None), ("", None)],
)
def test_macos_vram_units_are_parsed(text: str, expected: int | None) -> None:
    """Check: macos vram units are parsed."""
    assert profiles._parse_macos_vram_gb(text) == expected
