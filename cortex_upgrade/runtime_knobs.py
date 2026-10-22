"""Runtime-tunable knobs with bounds, defaults and an audit trail.

``RuntimeKnobs`` exists so the self-modification engine (see
``cortex_core.self_model``) has something honest to modify: in-process settings with
declared defaults and bounds, an applied-value view, and a change log. It never touches
environment variables or files, so a self-modification cannot outlive the process or leak
into the next one without an operator choosing so.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("cortex-upgrade.runtime-knobs")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RuntimeKnobs:
    DEFAULTS: dict[str, Any] = {
        "self_healing_enabled": True,
        "self_healing_interval_seconds": 30,
        "max_collaboration_rounds": 3,
    }

    def __init__(self, defaults: dict[str, Any] | None = None) -> None:
        self.defaults = dict(self.DEFAULTS)
        if defaults:
            self.defaults.update(defaults)
        self._values: dict[str, Any] = dict(self.defaults)
        self.changes: list[dict[str, Any]] = []

    def get(self, knob: str, fallback: Any = None) -> Any:
        return self._values.get(knob, fallback)

    def set(self, knob: str, value: Any, rationale: str = "") -> None:
        if knob not in self.defaults:
            raise KeyError(f"unknown knob '{knob}'")
        previous = self._values.get(knob)
        self._values[knob] = value
        record = {
            "knob": knob,
            "previous": previous,
            "value": value,
            "rationale": rationale,
            "at": _utcnow().isoformat(),
        }
        self.changes.append(record)
        self.changes = self.changes[-100:]
        logger.info("knob %s: %r -> %r (%s)", knob, previous, value, rationale)

    def reset(self, knob: str) -> Any:
        if knob not in self.defaults:
            raise KeyError(f"unknown knob '{knob}'")
        self.set(knob, self.defaults[knob], rationale="reset to default")
        return self.defaults[knob]

    def diff_from_defaults(self) -> dict[str, dict[str, Any]]:
        return {
            knob: {"default": self.defaults[knob], "current": value}
            for knob, value in self._values.items()
            if value != self.defaults[knob]
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "values": dict(self._values),
            "defaults": dict(self.defaults),
            "modified": self.diff_from_defaults(),
            "recent_changes": self.changes[-10:],
        }


# The one instance the running process actually consults (orchestrator budget, self-healing
# cadence). The API's self-modification engine mutates this object, so an approved knob
# change is felt by the live loop rather than being a decorative setting.
global_runtime_knobs = RuntimeKnobs()
