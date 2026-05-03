"""AI Agent module for natural language log querying."""

import os
import json
import re
import subprocess
import textwrap
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from openai import OpenAI

from loglens import config as cfg
from loglens import skills as skill_mod

_JQ_RULES = textwrap.dedent("""\
    ── JQ RULES (STRICT — DO NOT DEVIATE) ──
    Input:  A JSON array of log records.
    Output: A jq program inside a ```jq ... ``` code block.

    ALLOWED builtins ONLY:
      select, has, map, map_values, to_entries, from_entries,
      group_by, sort_by, unique_by, max_by, min_by, limit,
      length, type, keys, values, contains, test, ltrimstr, rtrimstr,
      ascii_downcase, ascii_upcase, split, join, flatten, first, last,
      range, indices, index, rindex, any, all, reduce, env, path,
      strings, numbers, booleans, nulls, arrays, objects, iterables,
      recurse, walk, leaf_paths, paths, del, add, not, empty, error,
      input, inputs, debug, halt, halt_error, isnan, isinfinite, isfinite,
      isnormal, infinite, nan, null, true, false, tojson, fromjson, tonumber,
      todate, fromdate, now, strftime, strptime, gmtime, mktime, dateadd,
      datesub, floor, ceil, round, sqrt, pow, log, exp, fabs, remainder,
      significand, exponent, logb, nearbyint, trunc, significand, nan,
      modulemeta, $__loc__, label, break, limit, until, while, repeat,
      try, catch, ?//, error, stderr, builtins, path, leaf_paths, getpath,
      setpath, delpaths, tostream, fromstream, truncate_stream, leaf_paths

    TIMESTAMP FILTERING (ISO 8601 strings):
      - Timestamps are stored as ISO 8601 strings (e.g., "2026-04-29T16:49:21.844Z").
      - To filter by time, compare strings lexicographically — ISO 8601 sorts correctly.
      - Example for "last 2 hours" — you must compute the cutoff statically using the
        most recent timestamp in the data, NOT a dynamic now() call:
          map(select(.timestamp != null and .timestamp >= "2026-04-29T15:00:00Z"))
      - Use the sample data timestamps to know the actual date range in the logs.
      - NEVER use parse_time(), hours_ago(), ago(), or any non-existent function.

    FILTERING:
      - Always use: map(select(...))
      - Case-insensitive string match: .field | test("pattern"; "i")
      - Level filtering: .level == "ERROR"
      - Null-safe: .field? // ""

    OUTPUT:
      - Return minimal, relevant data — never dump the whole array.
      - For counting: group_by(.field) | map({key: .[0].field, count: length})
      - For top-N: sort_by(.count) | reverse | limit(10; .[])

    DO NOT invent functions. If a builtin is not in the list above, do not use it.
""")

_SYNTHESIS_SYSTEM = textwrap.dedent("""\
    You are a senior log analyst acting as an AI Copilot.

    Answer format:
    1. Direct answer in 1-2 sentences (lead with the key finding).
    2. Supporting insights as bullet points (what + why + recommendation).
    3. Use flags: ⚠️ (critical), ✅ (good), 💡 (recommendation), 📊 (data point).

    CRITICAL RULES:
    - Your ONLY source of truth is the "Retrieved Data" section below. ALL numbers,
      endpoints, error counts, and claims MUST come from this data.
    - NEVER reference or reuse numbers, endpoints, or findings from the conversation
      history. The history is only provided for conversational flow — treat each
      question as an independent analysis against the Retrieved Data.
    - If "Retrieved Data" is empty or says "NO DATA FOUND", explicitly say no matching
      records were found and suggest what the user could try instead.
    - Be specific: use exact numbers, timestamps, and field values from the data.
    - Tone: Confident analyst.
""")


class LogAgent:
    """AI Agent that translates natural language queries into JQ programs and synthesizes insights."""

    MAX_RETRIES = 3

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """Initialize the agent.
        
        Reads api_key and model from ~/.loglens/config.json if not provided explicitly.
        """
        provider = cfg.get_active_provider()
        self.api_key = api_key or cfg.get_api_key(provider) or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                f"No API key for provider '{provider}'. "
                f"Run: loglens config set-key {provider} <key>"
            )
        self.model = model or cfg.get_model(provider)
        self.client = OpenAI(api_key=self.api_key)
        self.max_jq_bytes = cfg.load().get("max_jq_bytes", 200_000)

    def query(self,
              session_dir: Path,
              query_text: str,
              history: Optional[List[Dict[str, str]]] = None,
              forced_skill: Optional[str] = None) -> Dict[str, Any]:
        """Orchestrate the two-pass retrieval and synthesis."""
        history = history or []

        # Load session context
        schema_path  = session_dir / "schema.json"
        id_map_path  = session_dir / "id_map.json"
        records_path = session_dir / "records.json"

        with open(schema_path, "r") as f:
            schema_data = json.load(f)

        schema_text = self._format_schema(schema_data.get("fields", {}))

        # ── Skill detection ──
        registry = skill_mod.get_registry()
        if forced_skill:
            skill = registry.get(forced_skill)
            if not skill:
                raise ValueError(f"Skill '{forced_skill}' not found. Run: loglens skills list")
        else:
            skill = registry.detect(schema_text)

        domain_context = skill.domain_context
        jq_hints       = skill.jq_hints

        id_map_summary = ""
        if id_map_path.exists():
            with open(id_map_path, "r") as f:
                id_map_data = json.load(f)
                id_map_summary = self._format_id_map(id_map_data.get("field_to_ids", {}))

        # Two-Pass Retrieval
        jq_out, jq_prog, attempts = self._two_pass_retrieval(
            records_path, schema_text, query_text, domain_context, id_map_summary, jq_hints
        )

        # Synthesis — with hallucination guard
        answer = self._synthesize(query_text, jq_out, domain_context, id_map_summary, history)

        return {
            "answer":   answer,
            "jq_program": jq_prog,
            "attempts": attempts,
            "raw_data": jq_out,
            "skill":    skill.name,
        }

    # ── Pass 1: Explore to confirm field names ────────────────────────────────

    def _two_pass_retrieval(self,
                            records_path: Path,
                            schema_text: str,
                            query: str,
                            domain_ctx: str,
                            id_map_ctx: str,
                            jq_hints: str = "") -> Tuple[str, str, int]:
        """Pass 1: Explore — confirm real field names via sample.
           Pass 2: Extract — precise query with retry loop."""

        # ── Pass 1: Explore ──
        explore_query = (
            f"Sample 3 records most relevant to this query: '{query}'. "
            f"Include all fields. Do not filter by time yet — just show raw examples."
        )
        explore_jq, _ = self._generate_jq(schema_text, explore_query, domain_ctx, "", jq_hints=jq_hints)
        sample_out, sample_err = self._run_jq(explore_jq, records_path)

        sample_context = ""
        if sample_out and sample_out not in ("null", "[]", "{}"):
            sample_context = (
                f"\n\nPass 1 sample — use these EXACT field names and timestamp values:\n"
                f"{sample_out[:3000]}"
            )
        else:
            # Pass 1 itself failed — still proceed but warn the LLM
            sample_context = (
                f"\n\nPass 1 returned no data (error: {sample_err or 'empty'}). "
                f"Rely on the schema to determine exact field names."
            )

        # ── Pass 2: Extract with retry loop ──
        prev_attempts: List[Dict[str, str]] = []
        combined_ctx = id_map_ctx + sample_context
        total_attempts = 1  # Pass 1

        for attempt_num in range(1, self.MAX_RETRIES + 1):
            total_attempts += 1
            precise_jq, _ = self._generate_jq(
                schema_text, query, domain_ctx, combined_ctx,
                prev_attempts=prev_attempts,
                jq_hints=jq_hints,
            )
            final_out, err = self._run_jq(precise_jq, records_path)

            if final_out and final_out not in ("null", "[]", "{}") and not err:
                return final_out, precise_jq, total_attempts

            # Record the failure for the next retry
            prev_attempts.append({
                "jq": precise_jq,
                "error": err or f"Returned empty/null: {final_out!r}"
            })

        # Exhausted retries — return whatever we last got (could be empty)
        last_out, _ = self._run_jq(prev_attempts[-1]["jq"], records_path)
        return last_out or "", prev_attempts[-1]["jq"], total_attempts

    # ── JQ Code Generation ────────────────────────────────────────────────────

    def _generate_jq(self,
                     schema_text: str,
                     query: str,
                     domain_ctx: str,
                     extra_ctx: str,
                     prev_attempts: Optional[List[Dict[str, str]]] = None,
                     jq_hints: str = "") -> Tuple[str, int]:
        """Generate a JQ program using the LLM. Returns (jq_program, token_count)."""

        hints_block = f"\n\nSkill JQ Hints:\n{jq_hints}" if jq_hints else ""

        system_prompt = textwrap.dedent(f"""\
            You are an expert jq programmer and log analyst.

            {domain_ctx}

            {_JQ_RULES}{hints_block}
        """)

        user_content = (
            f"JSON Schema (field names and types):\n{schema_text}\n\n"
            f"{extra_ctx}\n\n"
            f"User query: {query}\n\n"
            f"Think briefly about which fields to use, then output ONLY the jq program."
        )

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        # Inject retry feedback
        if prev_attempts:
            for pa in prev_attempts:
                messages.append({"role": "assistant", "content": f"```jq\n{pa['jq']}\n```"})
                messages.append({
                    "role": "user",
                    "content": (
                        f"That jq failed or returned empty data.\n"
                        f"Error / output: {pa['error']}\n\n"
                        f"Common causes:\n"
                        f"  - Used a non-existent function (parse_time, hours_ago, etc.)\n"
                        f"  - Wrong field name — check the schema and sample above\n"
                        f"  - Timestamp comparison format mismatch\n\n"
                        f"Please write a corrected jq program."
                    )
                })

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0
        )

        content = resp.choices[0].message.content
        tokens = resp.usage.total_tokens if resp.usage else 0

        match = re.search(r"```(?:jq)?\n?(.*?)```", content, re.DOTALL)
        if match:
            return match.group(1).strip(), tokens
        # Fallback: strip backticks and return raw
        return content.strip("`").strip(), tokens

    # ── JQ Execution ─────────────────────────────────────────────────────────

    def _run_jq(self, jq_program: str, filepath: Path) -> Tuple[str, str]:
        """Execute JQ command on the records file."""
        try:
            result = subprocess.run(
                ["jq", "-c", jq_program, str(filepath)],
                capture_output=True, text=True, timeout=30
            )
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            return stdout, stderr
        except FileNotFoundError:
            return "", "jq not installed. Run: brew install jq"
        except subprocess.TimeoutExpired:
            return "", "jq timed out (30s). Try a more specific query."
        except Exception as e:
            return "", str(e)

    # ── Synthesis ─────────────────────────────────────────────────────────────

    def _synthesize(self,
                    query: str,
                    jq_out: str,
                    domain_ctx: str,
                    id_map_ctx: str,
                    history: List[Dict[str, str]]) -> str:
        """Turn JQ output into a natural language insight.
        
        If jq_out is empty, the LLM is explicitly told no data was found
        to prevent hallucination.
        
        History is condensed into a brief topic summary to provide conversational
        context without polluting the data interpretation.
        """
        # ── Hallucination guard ──
        is_empty = not jq_out or jq_out.strip() in ("", "null", "[]", "{}")
        data_section = (
            "NO DATA FOUND — the jq query returned no matching records."
            if is_empty
            else jq_out[:self.max_jq_bytes]
        )
        if len(jq_out) > self.max_jq_bytes:
            data_section += f"\n... [truncated — {len(jq_out):,} bytes total]"

        system_prompt = _SYNTHESIS_SYSTEM + f"\n\n{domain_ctx}\n\n{id_map_ctx}"

        # ── Condense history into a brief context summary ──
        # Instead of injecting full Q&A pairs (which biases the LLM toward
        # old data), we provide only a topic summary so the LLM understands
        # conversational flow without confusing old data with new data.
        history_summary = ""
        if history:
            topics = []
            for msg in history:
                if msg["role"] == "user":
                    topics.append(msg["content"])
            if topics:
                recent = topics[-3:]  # Last 3 questions only
                history_summary = (
                    "\n\nConversation context (previous topics the user asked about — "
                    "do NOT reuse any numbers or data from these, only use them to "
                    "understand what the user is referring to):\n"
                    + "\n".join(f"- {t}" for t in recent)
                )

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{history_summary}\n\nQuestion: {query}\n\nRetrieved Data:\n{data_section}"}
        ]

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.2
        )
        return resp.choices[0].message.content.strip()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _format_schema(self, fields: Dict[str, Any]) -> str:
        """Format the discovered schema for the prompt."""
        lines = []
        for field, meta in sorted(fields.items()):
            types = ", ".join(meta["types"])
            rate = meta["occurrence_rate"] * 100
            lines.append(f"- {field} ({types}) | present in {rate:.1f}% of records")
        return "\n".join(lines)

    def _format_id_map(self, field_to_ids: Dict[str, Any]) -> str:
        """Format ID map summary for the prompt."""
        if not field_to_ids:
            return ""
        lines = ["Available ID Fields (use these to correlate log records):"]
        for field, ids in field_to_ids.items():
            sample_ids = list(ids)[:3] if isinstance(ids, list) else ids[:3]
            lines.append(f"  - {field}: e.g. {', '.join(sample_ids)}")
        return "\n".join(lines)

    def _get_domain_context(self, schema_text: str) -> str:  # kept for backward compat
        """Deprecated — skill detection is now done in query(). Kept for compatibility."""
        return skill_mod.detect_skill(schema_text).domain_context
