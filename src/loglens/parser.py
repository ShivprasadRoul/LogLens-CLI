"""Log parsing module for converting raw logs to structured JSON."""

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Generator
from pathlib import Path

class LogParser:
    """Parses various log formats into structured JSON with streaming support."""

    def __init__(self):
        # Pattern for standard LEVEL:LOGGER:MESSAGE format
        self.level_pattern = re.compile(r'^(INFO|ERROR|WARNING|DEBUG|CRITICAL):([a-zA-Z0-9_\.]+):(.*)', re.DOTALL)
        
        # Timestamp patterns for extraction
        self.ts_patterns = [
            # ISO8601: 2024-01-15T10:32:00.123Z
            re.compile(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)'),
            # Common Log Format: 15/Jan/2024:10:32:00 +0000
            re.compile(r'(\d{2}/[a-zA-Z]{3}/\d{4}:\d{2}:\d{2}:\d{2} [+-]\d{4})'),
            # Simple Date Time: 2024-04-29 16:49:21
            re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'),
        ]

    def parse_file_stream(self, file_path: Path) -> Generator[Dict[str, Any], None, None]:
        """Stream lines from a file and yield structured records."""
        if not file_path.exists():
            raise FileNotFoundError(f"Log file not found: {file_path}")

        decoder = json.JSONDecoder()
        current_record: Optional[Dict[str, Any]] = None
        buffer = ""
        in_json = False

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                stripped = line.strip()
                
                # Handle potential JSON objects (including multiline)
                if stripped.startswith('{') or in_json:
                    buffer += line
                    try:
                        # Try to decode the buffer
                        obj, end_pos = decoder.raw_decode(buffer)
                        # If successful, yield the object and any pending record
                        if current_record:
                            yield current_record
                            current_record = None
                        
                        yield self._normalize_record(obj, raw=buffer[:end_pos])
                        
                        # Reset buffer with remainder
                        remainder = buffer[end_pos:].strip()
                        buffer = remainder
                        in_json = remainder.startswith('{')
                        if not in_json and remainder:
                            # If remainder is not JSON, process it normally in next steps
                            line = remainder
                        else:
                            continue
                    except json.JSONDecodeError:
                        # Not a complete JSON yet, keep buffering
                        in_json = True
                        continue

                # Not JSON or JSON remainder
                match = self.level_pattern.match(line)
                if match:
                    if current_record:
                        yield current_record
                    
                    level, logger, msg = match.groups()
                    current_record = {
                        "type": "app_log",
                        "level": level,
                        "logger": logger,
                        "message": msg.strip(),
                        "raw": line.strip()
                    }
                    # Extract timestamp from message if it exists
                    ts = self._extract_timestamp(msg)
                    if ts:
                        current_record["timestamp"] = ts
                
                elif current_record:
                    # Append to current multiline message (e.g. traceback)
                    current_record["message"] += "\n" + line.rstrip()
                
                else:
                    # Fallback for completely unknown lines
                    if stripped:
                        current_record = {
                            "type": "app_log",
                            "level": "UNKNOWN",
                            "logger": "unknown",
                            "message": stripped,
                            "raw": line.strip()
                        }
                        ts = self._extract_timestamp(line)
                        if ts:
                            current_record["timestamp"] = ts

            # Final flush
            if current_record:
                yield current_record

    def _extract_timestamp(self, text: str) -> Optional[str]:
        """Extract first matching timestamp from text."""
        for pattern in self.ts_patterns:
            match = pattern.search(text)
            if match:
                return match.group(1)
        return None

    def _normalize_record(self, record: Dict[str, Any], raw: str) -> Dict[str, Any]:
        """Normalize various log fields to the standard LogLens schema."""
        # Normalize Timestamp
        for ts_field in ["timestamp", "written_at", "time", "ts", "@timestamp"]:
            if ts_field in record and not record.get("timestamp"):
                record["timestamp"] = record[ts_field]
                break
        
        # Normalize Level
        level_val = record.get("level")
        for level_field in ["severity", "log_level", "priority"]:
            if level_field in record and not level_val:
                level_val = record[level_field]
                break
        if level_val:
            record["level"] = str(level_val).upper()

        # Normalize Message
        for msg_field in ["message", "msg", "log", "text"]:
            if msg_field in record and not record.get("message"):
                record["message"] = record[msg_field]
                break

        # Defaults
        record.setdefault("type", "app_log")
        record.setdefault("level", "INFO")
        record.setdefault("raw", raw.strip())
        
        # Try to extract timestamp from raw if still missing
        if not record.get("timestamp"):
            ts = self._extract_timestamp(raw)
            if ts:
                record["timestamp"] = ts

        return record

def parse_logs(input_file: str, output_file: str):
    """CLI-friendly wrapper to parse a file and save to JSON."""
    parser = LogParser()
    input_path = Path(input_file)
    
    print(f"Ingesting: {input_file}...")
    records = []
    for record in parser.parse_file_stream(input_path):
        records.append(record)
    
    print(f"Extracted {len(records)} records.")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(records, f, indent=4)
    print(f"Done. Saved to {output_file}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        parse_logs(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "output.json")
    else:
        # Default for local testing
        parse_logs("prodonehr.log", "prodonehr.json")
