from dataclasses import dataclass, asdict
from typing import Any, Dict

@dataclass
class FileDetectedEvent:
    file_path: str
    source_category: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class TextExtractedEvent:
    file_path: str
    text: str
    candidate_id: str
    source_category: str | None = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class EnrichmentCompleteEvent:
    candidate_id: str
    file_path: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
