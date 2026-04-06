"""
Soundblueprint DNA profile data models.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class DNAProfile:
    """DNA dimensions + completeness from Soundblueprint analysis."""
    dna: Dict[str, Dict[str, float]]
    completeness: float
    duration: float
    dimensions: List[str]
    sample_rate: int = 22050

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dna": self.dna,
            "completeness": self.completeness,
            "duration": self.duration,
            "dimensions": self.dimensions,
        }
