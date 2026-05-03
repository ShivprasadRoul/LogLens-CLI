"""ID mapping and entity relationship detection."""

import json
import re
from typing import Any, Dict, List, Optional, Set
from pathlib import Path

class IDMapper:
    """Builds and maintains ID maps for entity relationships."""

    def __init__(self):
        """Initialize the ID mapper.
        
        self.id_map: Maps a specific ID value (e.g., 'txn_123') to a list of record indices.
        self.field_to_ids: Maps an ID field name (e.g., 'correlation_id') to a set of all seen IDs of that type.
        """
        self.id_map: Dict[str, List[int]] = {}
        self.field_to_ids: Dict[str, Set[str]] = {}
        # Pattern to identify potential ID fields
        self.id_field_pattern = re.compile(r'.*(id|uuid|guid|key|token|hash).*', re.IGNORECASE)

    def process_records(self, records: List[Dict[str, Any]]) -> None:
        """Scan records for potential IDs and build the map."""
        for idx, record in enumerate(records):
            self._scan_record(record, idx)

    def _scan_record(self, data: Any, record_idx: int, prefix: str = "") -> None:
        """Recursively scan a record for fields that look like IDs."""
        if isinstance(data, dict):
            for key, value in data.items():
                full_key = f"{prefix}.{key}" if prefix else key
                
                # Check if this field name looks like an ID field
                if self.id_field_pattern.match(key) and isinstance(value, str) and len(value) > 4:
                    self._add_to_map(full_key, value, record_idx)
                
                # Also scan message/raw for IDs using regex if needed (future improvement)
                
                # Recurse
                if isinstance(value, (dict, list)):
                    self._scan_record(value, record_idx, full_key)
        elif isinstance(data, list):
            for item in data:
                self._scan_record(item, record_idx, prefix)

    def _add_to_map(self, field_name: str, id_value: str, record_idx: int) -> None:
        """Add an ID occurrence to the maps."""
        # Add to global ID map
        if id_value not in self.id_map:
            self.id_map[id_value] = []
        if record_idx not in self.id_map[id_value]:
            self.id_map[id_value].append(record_idx)
        
        # Add to field-specific set
        if field_name not in self.field_to_ids:
            self.field_to_ids[field_name] = set()
        self.field_to_ids[field_name].add(id_value)

    def find_linked_records(self, id_value: str) -> List[int]:
        """Return all record indices associated with a specific ID."""
        return self.id_map.get(id_value, [])

    def get_summary(self) -> Dict[str, Any]:
        """Return a summary of discovered IDs and their frequencies."""
        summary = {}
        for field, ids in self.field_to_ids.items():
            summary[field] = {
                "unique_count": len(ids),
                "sample_ids": list(ids)[:5]
            }
        return summary

    def save(self, output_path: Path) -> None:
        """Save ID map to file."""
        data = {
            "id_map": self.id_map,
            "field_to_ids": {k: list(v) for k, v in self.field_to_ids.items()}
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def load(self, input_path: Path) -> None:
        """Load ID map from file."""
        if not input_path.exists():
            return
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.id_map = {k: list(v) for k, v in data.get("id_map", {}).items()}
        self.field_to_ids = {k: set(v) for k, v in data.get("field_to_ids", {}).items()}

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        mapper = IDMapper()
        with open(sys.argv[1], "r") as f:
            records = json.load(f)
            mapper.process_records(records)
        
        print(f"Discovered {len(mapper.id_map)} unique IDs across {len(mapper.field_to_ids)} fields.")
        print(json.dumps(mapper.get_summary(), indent=2))
