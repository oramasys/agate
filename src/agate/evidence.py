"""Provenance for hardware-fit observations.

Agate classifies placement evidence; it does not turn it into an admission
claim.  In-process observations are therefore derived unless a collector binds
the exact observation to an aware collection timestamp.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
from typing import Callable, Literal

from .profiles import HardwareObservation


def canonical_observation_digest(observation: HardwareObservation) -> str:
    """Return the stable, domain-tagged digest for a hardware observation."""
    payload = {
        "domain": "agate.hardware-observation",
        "schema_version": 1,
        "observation": asdict(observation),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}"


@dataclass(frozen=True, slots=True)
class FitEvidence:
    classification: Literal["observed", "derived"]
    observation_digest: str
    observed_at: datetime | None
    collector: str | None

    def __post_init__(self) -> None:
        if self.classification == "observed":
            if not isinstance(self.collector, str) or not self.collector.strip():
                raise ValueError("observed fit evidence requires a collector identity")
            if not isinstance(self.observed_at, datetime) or self.observed_at.utcoffset() is None:
                raise ValueError("observed fit evidence requires an aware timestamp")
        elif self.classification == "derived":
            if self.collector is not None or self.observed_at is not None:
                raise ValueError("derived fit evidence cannot claim a collector or timestamp")
        else:
            raise ValueError(f"unsupported fit evidence classification: {self.classification!r}")

    @classmethod
    def derived(cls, observation: HardwareObservation) -> FitEvidence:
        return cls("derived", canonical_observation_digest(observation), None, None)

    @classmethod
    def observed(
        cls,
        observation: HardwareObservation,
        collector: str,
        clock: Callable[[], datetime],
    ) -> FitEvidence:
        return cls(
            "observed",
            canonical_observation_digest(observation),
            clock(),
            collector,
        )

    def covers(self, observation: HardwareObservation) -> bool:
        return self.observation_digest == canonical_observation_digest(observation)
