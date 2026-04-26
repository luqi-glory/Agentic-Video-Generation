"""Global memory pool for the video-generation agent workflow.

The memory pool stores the core script context produced by scriptwriter and
later consumed by director, actor, and editor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


MemorySection = Dict[str, Any]


@dataclass
class MemoryPool:
    """A lightweight global memory pool for one video project."""

    story: MemorySection = field(default_factory=dict)
    background: MemorySection = field(default_factory=dict)
    characters: List[MemorySection] = field(default_factory=list)
    metadata: MemorySection = field(default_factory=dict)

    def inject_script(
        self,
        *,
        user_prompt: str,
        story: MemorySection,
        background: MemorySection,
        characters: List[MemorySection],
        metadata: Optional[MemorySection] = None,
    ) -> None:
        """Inject scriptwriter output into the memory pool."""

        self.story = story or {}
        self.background = background or {}
        self.characters = characters or []
        self.metadata = {
            "user_prompt": user_prompt,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            **(metadata or {}),
        }

    def get_character(self, name: str) -> Optional[MemorySection]:
        """Return a character profile by name."""

        for character in self.characters:
            if character.get("name") == name or character.get("姓名") == name:
                return character
        return None

    def get_global_context(self) -> MemorySection:
        """Return the complete context for director script generation."""

        return {
            "story": self.story,
            "background": self.background,
            "characters": self.characters,
            "metadata": self.metadata,
        }

    def select_for_shot(self, shot_description: str = "") -> MemorySection:
        """Return compact context for a single downstream shot.

        Director can use this after it has generated each shot description.
        The method intentionally does not decide shot order, shot size, or shot
        duration because those belong to director.
        """

        return {
            "shot_description": shot_description,
            "story": self.story,
            "background": self.background,
            "characters": self.characters,
            "metadata": self.metadata,
        }

    def to_dict(self) -> MemorySection:
        """Serialize the memory pool."""

        return self.get_global_context()

    @classmethod
    def from_dict(cls, data: MemorySection) -> "MemoryPool":
        """Restore a memory pool from serialized data."""

        return cls(
            story=data.get("story", {}),
            background=data.get("background", {}),
            characters=data.get("characters", []),
            metadata=data.get("metadata", {}),
        )


GLOBAL_MEMORY = MemoryPool()


def inject_script_to_global_memory(
    *,
    user_prompt: str,
    story: MemorySection,
    background: MemorySection,
    characters: List[MemorySection],
    metadata: Optional[MemorySection] = None,
) -> MemoryPool:
    """Inject scriptwriter output into the module-level global memory pool."""

    GLOBAL_MEMORY.inject_script(
        user_prompt=user_prompt,
        story=story,
        background=background,
        characters=characters,
        metadata=metadata,
    )
    return GLOBAL_MEMORY


def get_global_memory() -> MemoryPool:
    """Return the module-level global memory pool."""

    return GLOBAL_MEMORY
