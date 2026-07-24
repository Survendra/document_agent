"""Bounded pipeline memory with explicit compaction and payload clearing."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineMemory:
    """Keeps verified artifacts while discarding large transient tool payloads."""

    char_budget: int
    facts: list[dict[str, Any]] = field(default_factory=list)
    summaries: list[str] = field(default_factory=list)
    _transient: dict[str, Any] = field(default_factory=dict, repr=False)

    def remember_fact(self, fact: dict[str, Any]) -> None:
        self.facts.append(fact)
        self.compact()

    def set_transient(self, key: str, value: Any) -> None:
        self._transient[key] = value

    def get_transient(self, key: str) -> Any:
        return self._transient.get(key)

    def clear_tools(self) -> None:
        """Clear raw OCR/LLM payloads after a stage has persisted its artifact."""
        self._transient.clear()

    def compact(self) -> None:
        encoded = json.dumps(self.facts, ensure_ascii=False, default=str)
        if len(encoded) <= self.char_budget:
            return

        keep_from = max(1, len(self.facts) // 2)
        compacted = self.facts[:-keep_from]
        self.summaries.append(
            json.dumps(
                {
                    "compacted_items": len(compacted),
                    "documents": sorted(
                        {
                            str(item.get("filename"))
                            for item in compacted
                            if item.get("filename")
                        }
                    ),
                    "note": "Detailed items remain in persisted stage outputs.",
                },
                ensure_ascii=False,
            )
        )
        self.facts = self.facts[-keep_from:]

    def prompt_context(self) -> str:
        payload = {"summaries": self.summaries, "recent_facts": self.facts}
        text = json.dumps(payload, ensure_ascii=False, default=str)
        return text[-self.char_budget :]
