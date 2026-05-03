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

    FUZZY MATCHING (CRITICAL):
      - When the user asks about an API/endpoint using informal names (e.g. "publish api",
        "import endpoint", "analytics service"), use `test()` with a substring pattern
        to match. NEVER hardcode exact endpoint paths — always use fuzzy matching.
      - Example: user says "publish api" → use: .request | test("publish"; "i")
      - Example: user says "import endpoint" → use: .request | test("import"; "i")
      - If unsure which field contains the target, search across multiple fields:
        select((.request? // "" | test("pattern"; "i")) or (.message? // "" | test("pattern"; "i")))

    OUTPUT STRATEGY:
      - PREFER SIMPLE QUERIES. Return the filtered records and let the synthesis
        step compute statistics. Do NOT attempt complex multi-step aggregations
        (group_by + from_entries + arithmetic) — these often fail silently.
      - GOOD: map(select(.request | test("publish"; "i"))) | map({request, method, response_status, response_time_ms})
      - BAD:  Complex 5-step pipeline with from_entries, $variables, and arithmetic
      - For counting/grouping, keep it to at most 2 steps:
          map(select(...)) | group_by(.field) | map({key: .[0].field, count: length})
      - For top-N: sort_by(.count) | reverse | limit(10; .[])
      - If the dataset is small (<100 filtered records), just return all matching records.

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
    - If "Retrieved Data" is empty or says "NO DATA FOUND":
      a) Check if a "Similar Data Found" section is provided below — if yes, show
         the user what similar/related data IS available and ask a clarifying question
         (e.g. "Did you mean one of these endpoints: /v1/study, /v1/media...?").
      b) If no similar data either, explicitly say no matching records were found and
         suggest what the user could try (e.g. different keywords, broader search).
    - When the user’s question is ambiguous or uses informal names, try to map their
      intent to the actual data. If you can’t, ASK a follow-up question rather than
      just saying "no data found".
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

        # ── Fuzzy discovery fallback ──
        # When retrieval returns empty, run a discovery query to find
        # related data so the synthesis can suggest alternatives.
        discovery_ctx = ""
        is_empty = not jq_out or jq_out.strip() in ("", "null", "[]", "{}")
        if is_empty:
            discovery_ctx = self._discover_related(
                records_path, schema_text, query_text, domain_context, jq_hints
            )

        # Synthesis — with hallucination guard
        answer = self._synthesize(
            query_text, jq_out, domain_context, id_map_summary, history, discovery_ctx
        )

        return {
            "answer":   answer,
            "jq_program": jq_prog,
            "attempts": attempts,
            "raw_data": jq_out,
            "skill":    skill.name,
        }

    def briefing(self,
                 session_dir: Path,
                 forced_skill: Optional[str] = None) -> Dict[str, Any]:
        """Run fast JQ scans at chat startup to surface key insights.

        No LLM call — pure JQ analysis. Returns:
          - total_records: int
          - error_count: int (4xx + 5xx)
          - error_5xx_count: int
          - failing_endpoints: list of {endpoint, method, errors}
          - recent_failure: dict or None
          - slow_endpoints: list of {endpoint, avg_ms}
          - skill: str
          - suggestions: list of question strings
        """
        import subprocess

        schema_path  = session_dir / "schema.json"
        records_path = session_dir / "records.json"

        if not records_path.exists():
            return {}

        with open(schema_path, "r") as f:
            schema_data = json.load(f)
        schema_text = self._format_schema(schema_data.get("fields", {}))

        registry = skill_mod.get_registry()
        skill = (
            registry.get(forced_skill)
            if forced_skill
            else registry.detect(schema_text)
        )

        def _jq(prog: str) -> str:
            try:
                r = subprocess.run(
                    ["jq", "-c", prog, str(records_path)],
                    capture_output=True, text=True, timeout=15
                )
                return r.stdout.strip()
            except Exception:
                return ""

        # ── Scan 1: Total records ──
        total_raw = _jq("length")
        total = int(total_raw) if total_raw.isdigit() else 0

        # ── Scan 2: Error counts (needs response_status field) ──
        has_status = "response_status" in schema_text
        has_level  = "level" in schema_text

        error_count  = 0
        error_5xx    = 0
        if has_status:
            cnt_raw = _jq("map(select(.response_status? >= 400)) | length")
            error_count = int(cnt_raw) if cnt_raw.isdigit() else 0
            cnt5_raw = _jq("map(select(.response_status? >= 500)) | length")
            error_5xx = int(cnt5_raw) if cnt5_raw.isdigit() else 0
        elif has_level:
            cnt_raw = _jq('map(select(.level? == "ERROR" or .level? == "CRITICAL")) | length')
            error_count = int(cnt_raw) if cnt_raw.isdigit() else 0

        # ── Scan 3: Failing endpoints ──
        failing_endpoints = []
        if has_status:
            fe_raw = _jq(
                'map(select(.response_status? >= 400 and .request? != null))'
                ' | group_by(.request)'
                ' | map({endpoint: .[0].request, method: .[0].method,'
                '        errors: length, sample_status: .[0].response_status})'
                ' | sort_by(.errors) | reverse | limit(3; .[])'
            )
            if fe_raw:
                import json as _json
                try:
                    for line in fe_raw.splitlines():
                        failing_endpoints.append(_json.loads(line))
                except Exception:
                    pass

        # ── Scan 4: Most recent failure ──
        recent_failure = None
        if has_status:
            rf_raw = _jq(
                'map(select(.response_status? >= 500 and .request? != null))'
                ' | sort_by(.timestamp?) | last'
            )
            if rf_raw and rf_raw not in ("null", ""):
                import json as _json
                try:
                    recent_failure = _json.loads(rf_raw)
                except Exception:
                    pass

        # ── Scan 5: Slow endpoints (if response_time_ms exists) ──
        slow_endpoints = []
        if "response_time_ms" in schema_text and has_status:
            slow_raw = _jq(
                'map(select(.response_time_ms? != null and .request? != null))'
                ' | group_by(.request)'
                ' | map({'
                '    endpoint: .[0].request,'
                '    avg_ms: (map(.response_time_ms | tonumber) | add / length | floor)'
                '  })'
                ' | sort_by(.avg_ms) | reverse | limit(3; .[])'
            )
            if slow_raw:
                import json as _json
                try:
                    for line in slow_raw.splitlines():
                        slow_endpoints.append(_json.loads(line))
                except Exception:
                    pass

        # ── Build smart suggestions ──
        suggestions = []
        if failing_endpoints:
            ep = failing_endpoints[0]["endpoint"].split("/")[-1]
            suggestions.append(f"why did {ep} api fail?")
        if error_5xx > 0:
            suggestions.append("show me all server errors")
        if slow_endpoints:
            ep = slow_endpoints[0]["endpoint"].split("/")[-1]
            suggestions.append(f"why is {ep} so slow?")
        if failing_endpoints and len(failing_endpoints) > 1:
            suggestions.append("which endpoint is most unstable?")
        if not suggestions:
            suggestions = ["show recent errors", "what failed in the last hour?"]

        return {
            "total":             total,
            "error_count":       error_count,
            "error_5xx":         error_5xx,
            "failing_endpoints": failing_endpoints,
            "recent_failure":    recent_failure,
            "slow_endpoints":    slow_endpoints,
            "skill":             skill.name,
            "suggestions":       suggestions[:4],
        }


    def _two_pass_retrieval(self,
                            records_path: Path,
                            schema_text: str,
                            query: str,
                            domain_ctx: str,
                            id_map_ctx: str,
                            jq_hints: str = "") -> Tuple[str, str, int]:
        """Pass 1: Explore — confirm real field names via sample.
           Pass 2: Extract — precise query with retry loop."""

        # ── Pass 1: Keyword-aware Explore ──
        # Instead of asking the LLM to "sample 3 relevant records" (which often
        # misses the target), we extract keywords from the user's query and
        # instruct the LLM to search for them across multiple fields.
        explore_query = (
            f"The user asked: '{query}'. "
            f"Find records that match ANY keyword from the question. "
            f"Search across .request, .message, .msg, .logger, and .raw fields "
            f"using case-insensitive substring matching (test/contains). "
            f"Return up to 5 matching records with ALL their fields. "
            f"If no keyword match is found, sample 3 random records instead."
        )
        explore_jq, _ = self._generate_jq(schema_text, explore_query, domain_ctx, "", jq_hints=jq_hints)
        sample_out, sample_err = self._run_jq(explore_jq, records_path)

        sample_context = ""
        if sample_out and sample_out not in ("null", "[]", "{}"):
            sample_context = (
                f"\n\nPass 1 sample — use these EXACT field names, values, and structure:\n"
                f"{sample_out[:3000]}"
            )
        else:
            # Pass 1 itself failed — still proceed but warn the LLM
            sample_context = (
                f"\n\nPass 1 returned no data (error: {sample_err or 'empty'}). "
                f"Rely on the schema to determine exact field names."
            )

        # ── Pass 2: Extract with retry loop ──
        # Emphasize: return ALL matching records, let synthesis compute stats.
        augmented_query = (
            f"{query}\n\n"
            f"IMPORTANT INSTRUCTIONS FOR JQ:\n"
            f"1. Return ALL records matching the user's target (endpoint, logger, etc.) — "
            f"do NOT pre-filter by response_status, level, or error type.\n"
            f"2. Include key fields: request, method, response_status, response_time_ms, "
            f"timestamp, level, message, correlation_id (whichever exist).\n"
            f"3. Do NOT compute failure rates, percentages, or aggregations in JQ.\n"
            f"4. Keep the query simple: map(select(...)) | map({{field1, field2, ...}})"
        )
        prev_attempts: List[Dict[str, str]] = []
        combined_ctx = id_map_ctx + sample_context
        total_attempts = 1  # Pass 1

        for attempt_num in range(1, self.MAX_RETRIES + 1):
            total_attempts += 1
            precise_jq, _ = self._generate_jq(
                schema_text, augmented_query, domain_ctx, combined_ctx,
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

    def _discover_related(self,
                          records_path: Path,
                          schema_text: str,
                          query: str,
                          domain_ctx: str,
                          jq_hints: str) -> str:
        """When the main query returned empty, run a broader discovery query
        to find similar/related data the user might have been looking for.
        
        Returns a context string with discovered alternatives, or "".
        """
        discovery_prompt = (
            f"The user asked: '{query}' but no exact match was found. "
            f"Generate a JQ program that finds potentially RELATED data. "
            f"For example: list all unique values of .request (API endpoints), "
            f"or unique .logger values, or unique .message patterns that might be "
            f"related to what the user is looking for. Show up to 20 unique values. "
            f"Return a compact JSON array or object."
        )
        try:
            discovery_jq, _ = self._generate_jq(
                schema_text, discovery_prompt, domain_ctx, "", jq_hints=jq_hints
            )
            discovery_out, _ = self._run_jq(discovery_jq, records_path)
            if discovery_out and discovery_out.strip() not in ("", "null", "[]", "{}"):
                return discovery_out[:3000]
        except Exception:
            pass
        return ""

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
                    history: List[Dict[str, str]],
                    discovery_ctx: str = "") -> str:
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

        # Add discovery context when main query returned empty
        discovery_section = ""
        if discovery_ctx:
            discovery_section = (
                f"\n\nSimilar Data Found (the exact query returned no results, "
                f"but here is related data from the logs that might help — "
                f"use this to suggest what the user might have meant):\n"
                f"{discovery_ctx}"
            )

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
            {"role": "user", "content": f"{history_summary}\n\nQuestion: {query}\n\nRetrieved Data:\n{data_section}{discovery_section}"}
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
