"""Gene schema: axes, allowed values, coherence rules, ordinal ordering."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GeneSchema:
    name: str
    axes: dict[str, list[str]]
    ordinal_axes: dict[str, list[str]] = field(default_factory=dict)
    coherence: list[dict[str, Any]] = field(default_factory=list)
    open_axes: bool = False
    # Phase 9: track values/axes that were registered after load (LLM-proposed
    # discoveries vs the schema's original closed set). Reporters surface
    # these to highlight where evolution invented something new.
    discovered_values: dict[str, list[str]] = field(default_factory=dict)
    discovered_axes: list[str] = field(default_factory=list)

    @staticmethod
    def load(path: str | Path) -> "GeneSchema":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return GeneSchema(
            name=data["name"],
            axes={k: list(v) for k, v in data["axes"].items()},
            ordinal_axes={k: list(v) for k, v in data.get("ordinal_axes", {}).items()},
            coherence=list(data.get("coherence", [])),
            open_axes=bool(data.get("open_axes", False)),
        )

    def register_value(self, axis: str, value: str) -> bool:
        """Add `value` to the allowed list of `axis`, returning True if it
        was actually new. No-op if open_axes is False or value already exists."""
        if not self.open_axes:
            return False
        if axis not in self.axes:
            return False
        if value in self.axes[axis]:
            return False
        self.axes[axis].append(value)
        self.discovered_values.setdefault(axis, []).append(value)
        return True

    def register_axis(self, name: str, values: list[str]) -> bool:
        """Add a brand-new axis with its initial value list. Returns True if
        the axis was actually added (False if open_axes=False or already exists)."""
        if not self.open_axes:
            return False
        if name in self.axes:
            return False
        self.axes[name] = list(values)
        self.discovered_axes.append(name)
        return True

    def axis_names(self) -> list[str]:
        return list(self.axes.keys())

    def is_valid_value(self, axis: str, value: str) -> bool:
        if axis not in self.axes:
            return self.open_axes
        return value in self.axes[axis] or self.open_axes

    def coherence_violations(self, genome: dict[str, str]) -> list[str]:
        problems: list[str] = []
        for rule in self.coherence:
            cond = rule.get("if", {})
            if not all(genome.get(k) == v for k, v in cond.items()):
                continue
            for k, v in rule.get("then", {}).items():
                if genome.get(k) != v:
                    problems.append(f"{cond} => {k}={v} (got {genome.get(k)})")
            for k, allowed in rule.get("then_in", {}).items():
                if genome.get(k) not in allowed:
                    problems.append(f"{cond} => {k} in {allowed} (got {genome.get(k)})")
            for k, forbidden in rule.get("then_not", {}).items():
                if genome.get(k) == forbidden:
                    problems.append(f"{cond} => {k} != {forbidden}")
            for k, min_value in rule.get("then_min", {}).items():
                ord_list = self.ordinal_axes.get(k)
                if not ord_list:
                    continue
                got = genome.get(k)
                if got not in ord_list or ord_list.index(got) < ord_list.index(min_value):
                    problems.append(f"{cond} => {k} >= {min_value} (got {got})")
        return problems

    def is_coherent(self, genome: dict[str, str]) -> bool:
        return not self.coherence_violations(genome)

    def ordinal_index(self, axis: str, value: str) -> int | None:
        order = self.ordinal_axes.get(axis)
        if order is None or value not in order:
            return None
        return order.index(value)
