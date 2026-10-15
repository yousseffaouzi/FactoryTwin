"""Deterministic synthetic quality scenarios for the software-only simulator."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

from .blueprint import FactoryBlueprint, NAME

WORKPIECE_ID = re.compile(r"WP-(\d{4,})\Z")
QUALITY_OUTCOMES = ("GOOD", "SCRAP", "REWORK")
MAX_QUALITY_DECISIONS = 10_000
MAX_QUALITY_ATTEMPTS = 10_000


@dataclass(frozen=True, order=True)
class QualityDecision:
    workpiece_id: str
    station: str
    attempt: int
    outcome: str

    def to_dict(self) -> dict:
        return {
            "workpiece_id": self.workpiece_id,
            "station": self.station,
            "attempt": self.attempt,
            "outcome": self.outcome,
        }


@dataclass(frozen=True)
class QualityScenario:
    """Strict, finite quality decisions; unspecified attempts default to GOOD."""

    decisions: tuple[QualityDecision, ...] = ()

    @property
    def enabled(self) -> bool:
        return bool(self.decisions)

    def to_dict(self) -> dict:
        return {"version": 1, "decisions": [decision.to_dict() for decision in self.decisions]}

    def lookup(self) -> dict[tuple[str, str, int], str]:
        return {(d.workpiece_id, d.station, d.attempt): d.outcome for d in self.decisions}

    def validate_for_blueprint(self, blueprint: FactoryBlueprint) -> None:
        unknown = sorted({d.station for d in self.decisions if d.station not in blueprint.station_ids})
        if unknown:
            raise ValueError(f"quality scenario references unknown station: {unknown[0]}")

    @classmethod
    def from_dict(cls, data: dict) -> QualityScenario:
        if (not isinstance(data, dict) or set(data) != {"version", "decisions"} or
                type(data["version"]) is not int or data["version"] != 1 or
                not isinstance(data["decisions"], list) or
                len(data["decisions"]) > MAX_QUALITY_DECISIONS):
            raise ValueError("invalid quality scenario header")
        decisions: list[QualityDecision] = []
        keys: set[tuple[str, str, int]] = set()
        for item in data["decisions"]:
            if (not isinstance(item, dict) or
                    set(item) != {"workpiece_id", "station", "attempt", "outcome"}):
                raise ValueError("invalid quality decision")
            workpiece_id = item["workpiece_id"]
            station = item["station"]
            attempt = item["attempt"]
            outcome = item["outcome"]
            match = WORKPIECE_ID.fullmatch(workpiece_id) if isinstance(workpiece_id, str) else None
            if match is None or int(match.group(1)) < 1:
                raise ValueError("invalid quality workpiece_id")
            if not isinstance(station, str) or NAME.fullmatch(station) is None:
                raise ValueError("invalid quality station")
            if type(attempt) is not int or not 1 <= attempt <= MAX_QUALITY_ATTEMPTS:
                raise ValueError("invalid quality attempt")
            if not isinstance(outcome, str) or outcome not in QUALITY_OUTCOMES:
                raise ValueError("invalid quality outcome")
            key = (workpiece_id, station, attempt)
            if key in keys:
                raise ValueError("duplicate quality decision")
            keys.add(key)
            decisions.append(QualityDecision(workpiece_id, station, attempt, outcome))
        decisions.sort(key=lambda d: (int(d.workpiece_id[3:]), d.station, d.attempt, d.outcome))
        return cls(tuple(decisions))

    @classmethod
    def load(cls, path: str | Path) -> QualityScenario:
        """Load a local scenario file; no random, remote or hardware input is used."""
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"unable to load quality scenario: {exc}") from exc
        return cls.from_dict(data)


DEFAULT_QUALITY_SCENARIO = QualityScenario()
