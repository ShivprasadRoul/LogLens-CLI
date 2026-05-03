"""One-shot patcher — run and delete."""
import pathlib

agent_path = pathlib.Path(__file__).parent / "agent.py"
content = agent_path.read_text(encoding="utf-8")

# Locate the block boundaries
start_marker = '_SYNTHESIS_SYSTEM = textwrap.dedent('
end_marker = '\n\n\nclass LogAgent'

si = content.find(start_marker)
ei = content.find(end_marker)
assert si != -1 and ei != -1, f"markers not found si={si} ei={ei}"

# Build the new prompt entirely from escaped unicode so no source encoding issues
warn  = "\u26a0\ufe0f"
ok    = "\u2705"
tip   = "\ud83d\udca1"
data  = "\ud83d\udcca"

new_prompt = (
    '_SYNTHESIS_SYSTEM = textwrap.dedent("""\\\n'
    "    You are a senior log analyst acting as an AI Copilot.\n"
    "\n"
    "    You MUST respond using EXACTLY this structure with these section headers:\n"
    "\n"
    "    ANSWER:\n"
    "    <Direct answer in 1-2 sentences. Lead with the key finding.>\n"
    "\n"
    "    DETAILS:\n"
    f"    <Supporting bullet points. Use flags:\n"
    f"      {warn} critical  {ok} healthy  {tip} recommendations  {data} data points>\n"
    "\n"
    "    EVIDENCE:\n"
    "    <Exact lines copied verbatim from the Retrieved Data that prove your answer.\n"
    "     Format: [timestamp]  description\n"
    "     Examples:\n"
    "       [2026-04-30T06:45:38]  PUT /v1/study/publish -> 500  |  response_time_ms: 167\n"
    "       [2026-04-30T06:45:38]  ERROR: Object of type StudyModel is not JSON serializable\n"
    "     Rules:\n"
    "     - ONLY copy values that appear verbatim in the Retrieved Data. Never paraphrase.\n"
    "     - Show 2-5 lines max. Pick the most diagnostic ones.\n"
    "     - If Retrieved Data is empty: write (no evidence -- query returned no records)\n"
    "    >\n"
    "\n"
    "    CRITICAL RULES:\n"
    '    - Your ONLY source of truth is the \\"Retrieved Data\\" section. ALL numbers,\n'
    "      endpoints, error counts, and claims MUST come from this data.\n"
    "    - NEVER reference or reuse numbers, endpoints, or findings from conversation\n"
    "      history. History is only for conversational flow.\n"
    '    - If \\"Retrieved Data\\" is empty or says \\"NO DATA FOUND\\":\n'
    '      a) If a \\"Similar Data Found\\" section exists, show what IS available and ask\n'
    '         a clarifying question (e.g. \\"Did you mean /v1/study or /v1/media?\\").\n'
    "      b) Otherwise say no records found and suggest alternative search terms.\n"
    "    - When the question is ambiguous, map intent to actual data or ask a follow-up.\n"
    "    - Tone: Confident analyst.\n"
    '""")'
)

new_content = content[:si] + new_prompt + content[ei:]
agent_path.write_text(new_content, encoding="utf-8")
print(f"Done. File now {len(new_content.splitlines())} lines.")
