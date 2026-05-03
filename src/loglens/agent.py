"""AI Agent module for natural language log querying."""

import os
import json
import re
import subprocess
import textwrap
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from openai import OpenAI

class LogAgent:
    """AI Agent that translates natural language queries into JQ programs and synthesizes insights."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o"):
        """Initialize the agent with OpenAI client."""
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY environment variable.")
        
        self.client = OpenAI(api_key=self.api_key)
        self.model = model
        self.max_jq_bytes = 200_000

    def query(self, 
              session_dir: Path, 
              query_text: str, 
              history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        """Orchestrate the two-pass retrieval and synthesis."""
        history = history or []
        
        # Load session context
        schema_path = session_dir / "schema.json"
        id_map_path = session_dir / "id_map.json"
        records_path = session_dir / "records.json"
        
        with open(schema_path, "r") as f:
            schema_data = json.load(f)
        
        # Build context strings
        schema_text = self._format_schema(schema_data.get("fields", {}))
        
        # Detect domain (simplified for now)
        domain_context = self._get_domain_context(schema_text)
        
        # Load ID Map (simplified summary for context)
        id_map_summary = ""
        if id_map_path.exists():
            with open(id_map_path, "r") as f:
                id_map_data = json.load(f)
                id_map_summary = self._format_id_map(id_map_data.get("field_to_ids", {}))

        # 1. Two-Pass Retrieval
        jq_out, jq_prog, attempts = self._two_pass_retrieval(
            records_path, schema_text, query_text, domain_context, id_map_summary
        )
        
        # 2. Synthesis
        answer = self._synthesize(
            query_text, jq_out, domain_context, id_map_summary, history
        )
        
        return {
            "answer": answer,
            "jq_program": jq_prog,
            "attempts": attempts,
            "raw_data": jq_out
        }

    def _two_pass_retrieval(self, 
                            records_path: Path, 
                            schema_text: str, 
                            query: str, 
                            domain_ctx: str, 
                            id_map_ctx: str) -> Tuple[str, str, int]:
        """Pass 1: Explore field names. Pass 2: Extract data."""
        
        # Pass 1: Explore
        explore_query = f"Give a broad sample (2-3 records) relevant to: {query}. Include all fields."
        explore_jq = self._generate_jq(schema_text, explore_query, domain_ctx, id_map_ctx)
        sample_out, _ = self._run_jq(explore_jq, records_path)
        
        sample_context = ""
        if sample_out and sample_out not in ("null", "[]", "{}"):
            sample_context = f"\n\nConfirmed sample data (use these exact field names):\n{sample_out[:2000]}"

        # Pass 2: Extract
        precise_jq = self._generate_jq(schema_text, query, domain_ctx, id_map_ctx + sample_context)
        final_out, err = self._run_jq(precise_jq, records_path)
        
        if not final_out or final_out in ("null", "[]", "{}"):
            # One retry if failed
            retry_jq = self._generate_jq(schema_text, query, domain_ctx, id_map_ctx + sample_context, 
                                        error=err or "Empty result")
            final_out, _ = self._run_jq(retry_jq, records_path)
            return final_out, retry_jq, 2
            
        return final_out, precise_jq, 1

    def _generate_jq(self, 
                    schema_text: str, 
                    query: str, 
                    domain_ctx: str, 
                    id_map_ctx: str,
                    error: Optional[str] = None) -> str:
        """Generate a JQ program using the LLM."""
        
        system_prompt = textwrap.dedent(f"""\
            You are an expert jq programmer and log analyst.
            
            {domain_ctx}
            
            {id_map_ctx}
            
            jq Rules:
            - Input is a JSON array of log records.
            - Output your final jq program inside a ```jq ... ``` code block.
            - Use map(select(...)) for filtering.
            - Never dump the whole file. Return minimal, relevant slice.
            - For case-insensitive matching: test("pattern"; "i").
            - If you see nested fields, use dot notation (e.g., .user.id).
        """)

        user_content = f"JSON Schema:\n{schema_text}\n\nUser query: {query}"
        if error:
            user_content += f"\n\nPrevious attempt failed with error/empty result: {error}. Please fix the jq."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0
        )

        content = resp.choices[0].message.content
        match = re.search(r"```(?:jq)?\n?(.*?)```", content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return content.strip("`").strip()

    def _run_jq(self, jq_program: str, filepath: Path) -> Tuple[str, str]:
        """Execute JQ command on the file."""
        try:
            # We use -c for compact output to handle potentially large results
            result = subprocess.run(
                ["jq", "-c", jq_program, str(filepath)],
                capture_output=True, text=True, timeout=30
            )
            return result.stdout.strip(), result.stderr.strip()
        except Exception as e:
            return "", str(e)

    def _synthesize(self, 
                   query: str, 
                   jq_out: str, 
                   domain_ctx: str, 
                   id_map_ctx: str, 
                   history: List[Dict[str, str]]) -> str:
        """Turn JQ output into a natural language insight."""
        
        system_prompt = textwrap.dedent(f"""\
            You are a senior log analyst acting as an AI Copilot.
            
            {domain_ctx}
            
            Answer format:
            1. Direct answer in 1-2 sentences.
            2. Supporting insights as bullet points (what + why + recommendation).
            3. Use flags: ⚠️ (critical), ✅ (good), 💡 (recommendation), 📊 (data point).
            
            Rules:
            - Use human-readable names from the ID map if provided.
            - Be specific with numbers and timestamps.
            - Tone: Confident analyst.
        """)

        messages = [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": f"Question: {query}\n\nRetrieved Data:\n{jq_out[:100000]}"}
        ]

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.3
        )
        return resp.choices[0].message.content.strip()

    def _format_schema(self, fields: Dict[str, Any]) -> str:
        """Format the discovered schema for the prompt."""
        lines = []
        for field, meta in sorted(fields.items()):
            types = ", ".join(meta["types"])
            rate = meta["occurrence_rate"] * 100
            lines.append(f"- {field} ({types}) | present in {rate:.1f}% of logs")
        return "\n".join(lines)

    def _format_id_map(self, field_to_ids: Dict[str, List[str]]) -> str:
        """Format ID map summary for the prompt."""
        if not field_to_ids:
            return ""
        lines = ["Available ID Fields (use these to correlate logs):"]
        for field, ids in field_to_ids.items():
            samples = ", ".join(ids[:3])
            lines.append(f"  - {field}: samples [{samples}]")
        return "\n".join(lines)

    def _get_domain_context(self, schema_text: str) -> str:
        """Simple domain detection logic (can be expanded)."""
        if "usability_score" in schema_text or "miss_clicks" in schema_text:
            return "DOMAIN: UX Prototype Testing. Focus on usability scores, miss clicks, and drop-offs."
        if "response_status" in schema_text or "remote_ip" in schema_text:
            return "DOMAIN: API/Web Server Logs. Focus on HTTP status codes, latency, and error patterns."
        return "DOMAIN: General Application Logs."
