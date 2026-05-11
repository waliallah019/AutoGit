import asyncio
import subprocess
import os
import re
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_groq import ChatGroq

load_dotenv()

# ── constants ──────────────────────────────────────────────────────────────────
MAX_RAW_LINES_PER_CHUNK = 120   # split large files into sub-chunks at this size
MAX_CHUNK_CONTEXT       = 3000  # chars fed to each chunk agent
MAX_FINAL_CONTEXT       = 6000  # chars fed to the final commit agent

IGNORE_PATTERNS = [
    '__pycache__', '.pyc', '.pyo', '.pyd', '.so', '.dll', '.class', '.o',
    'node_modules', '.git/', 'package-lock.json', 'yarn.lock', '.DS_Store',
    '.lock', 'dist/', 'build/', '.egg-info',
]


# ── helpers ────────────────────────────────────────────────────────────────────

def _should_ignore(filepath: str) -> bool:
    return any(p in filepath for p in IGNORE_PATTERNS)


def _get_file_type(filepath: str) -> str:
    fp = filepath.lower()
    if '.py'   in fp: return 'python'
    if any(e in fp for e in ['.js', '.jsx', '.ts', '.tsx']): return 'javascript'
    if '.java' in fp: return 'java'
    if any(e in fp for e in ['.md', '.txt', '.rst']):        return 'docs'
    if any(e in fp for e in ['.json', '.yaml', '.yml', '.toml', '.ini']): return 'config'
    if any(e in fp for e in ['.html', '.css', '.scss']):     return 'frontend'
    if 'test' in fp or 'spec' in fp:                         return 'test'
    return 'other'


def _split_diff_by_file(diff_output: str) -> list:
    """
    Split raw git diff output into one dict per file.
    Each dict has: filepath, basename, file_type, additions, deletions, raw_lines (list).
    Ignored files are skipped entirely.
    """
    chunks = []
    current = None

    for line in diff_output.splitlines():
        if line.startswith('diff --git'):
            if current and not _should_ignore(current['filepath']):
                chunks.append(current)
            m = re.search(r'b/(.+)$', line)
            filepath = m.group(1) if m else 'unknown'
            current = {
                'filepath':  filepath,
                'basename':  os.path.basename(filepath),
                'file_type': _get_file_type(filepath),
                'additions': 0,
                'deletions': 0,
                'raw_lines': [],
            }
        elif current and not _should_ignore(current['filepath']):
            if line.startswith('+') and not line.startswith('+++'):
                current['additions'] += 1
            elif line.startswith('-') and not line.startswith('---'):
                current['deletions'] += 1
            if (line.startswith('+') and not line.startswith('+++')) or \
               (line.startswith('-') and not line.startswith('---')) or \
               line.startswith('@@'):
                current['raw_lines'].append(line)

    if current and not _should_ignore(current['filepath']):
        chunks.append(current)

    return chunks


def _sub_chunk(raw_lines: list, max_lines: int) -> list:
    """Split a file's diff lines into sub-chunks when the file is very large."""
    return [raw_lines[i:i + max_lines] for i in range(0, len(raw_lines), max_lines)]


def _make_llm(max_tokens: int = 200) -> ChatGroq:
    return ChatGroq(
        model="llama-3.1-8b-instant",
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=0.1,
        max_tokens=max_tokens,
    )


# ── parallel chunk agents ──────────────────────────────────────────────────────

async def _chunk_agent(file_chunk: dict, sub_lines: list, sub_idx: int, total_subs: int) -> str:
    """
    One async agent that summarises a single file (or sub-chunk of a large file).
    Returns a plain-English sentence describing what changed and why it matters.
    """
    raw_text = '\n'.join(sub_lines)
    if len(raw_text) > MAX_CHUNK_CONTEXT:
        raw_text = raw_text[:MAX_CHUNK_CONTEXT] + '\n[truncated]'

    sub_note = f" (part {sub_idx + 1}/{total_subs})" if total_subs > 1 else ""
    prompt = f"""You are a code reviewer analysing a git diff chunk.

FILE: {file_chunk['basename']}{sub_note}  |  type: {file_chunk['file_type']}  |  +{file_chunk['additions']} -{file_chunk['deletions']} lines

RAW DIFF LINES:
{raw_text}

Describe WHAT changed and WHY it matters in 1-2 concise sentences.
- Be specific: mention actual function names, variable names, or logic that changed.
- Do NOT say "the diff shows" or "lines were added/removed" — describe the change itself.
- Output ONLY the description. No preamble, no bullet points."""

    loop = asyncio.get_event_loop()
    llm  = _make_llm(max_tokens=120)

    try:
        response = await loop.run_in_executor(None, llm.invoke, prompt)
        summary  = response.content.strip().splitlines()[0].strip()
        return f"[{file_chunk['basename']}] {summary}"
    except Exception as e:
        return f"[{file_chunk['basename']}] +{file_chunk['additions']}/-{file_chunk['deletions']} lines changed ({file_chunk['file_type']})"


async def _run_chunk_agents(file_chunks: list) -> list:
    """
    Launch one async task per file (or sub-chunk for large files).
    All tasks run in parallel via asyncio.gather.
    """
    tasks = []

    for fc in file_chunks:
        sub_chunks = _sub_chunk(fc['raw_lines'], MAX_RAW_LINES_PER_CHUNK)
        if not sub_chunks:
            sub_chunks = [[]]
        for idx, sub in enumerate(sub_chunks):
            tasks.append(_chunk_agent(fc, sub, idx, len(sub_chunks)))

    print(f"   ⚡ Launching {len(tasks)} parallel chunk agent(s)...")
    summaries = await asyncio.gather(*tasks)
    return list(summaries)


# ── summary merger ─────────────────────────────────────────────────────────────

def _merge_summaries(summaries: list, file_chunks: list) -> str:
    """
    Combine all chunk summaries into a single context string for the final agent.
    Stays under MAX_FINAL_CONTEXT chars.
    """
    total_adds = sum(f['additions'] for f in file_chunks)
    total_dels = sum(f['deletions'] for f in file_chunks)

    header = (
        f"TOTAL CHANGES: {len(file_chunks)} file(s) | +{total_adds} -{total_dels} lines\n\n"
        f"PER-FILE SUMMARIES:\n"
    )

    body = '\n'.join(f"  • {s}" for s in summaries)
    result = header + body

    if len(result) > MAX_FINAL_CONTEXT:
        result = result[:MAX_FINAL_CONTEXT] + '\n[truncated]'

    return result


# ── final commit agent ─────────────────────────────────────────────────────────

def _final_commit_agent(merged_summary: str, total_files: int) -> str | None:
    """
    Read the merged summary of all chunk agents and produce one commit message.
    """
    print('\n📋 Merged summary sent to final agent:\n' + '─' * 60)
    print(merged_summary)
    print('─' * 60 + '\n')

    prompt = f"""You are a Git commit message generator. Output ONLY the commit message — nothing else.

CHANGE SUMMARY (produced by per-file analysis agents):
{merged_summary}

RULES:
- Format: <type>(<scope>): <description>
- Types: feat | fix | refactor | docs | style | test | chore | perf
- Max 70 characters total, imperative mood
- Identify the PRIMARY purpose that ties all changes together
- Reference actual function/class/variable names when relevant
- ONE LINE ONLY. No preamble. No explanation. No quotes. Just the raw commit message.

Good examples:
  refactor(commit_tool): replace priority bucketing with parallel chunk agents
  feat(auth): add JWT refresh token with expiry validation
  fix(parser): correct intent detection order for structural vs import changes

Commit message:"""

    llm = _make_llm(max_tokens=80)

    try:
        response = llm.invoke(prompt)
        if not response.content:
            return None

        lines   = [l.strip().strip('"').strip("'") for l in response.content.strip().splitlines() if l.strip()]
        message = lines[-1] if lines else ""

        # Reject preamble leakage
        preamble_signs = ['based on', 'here is', "here's", 'the commit', 'possible commit', 'i would', 'according to']
        if any(s in message.lower() for s in preamble_signs):
            return None

        # Reject vague / too short
        vague = ['update files', 'modify code', 'change code', 'update code', 'various changes']
        if any(w in message.lower() for w in vague) or len(message) < 20:
            return None

        return message

    except Exception as e:
        print(f"⚠ Final agent error: {e}")
        return None


# ── fallback ───────────────────────────────────────────────────────────────────

def _fallback_message(file_chunks: list) -> str:
    """Rule-based fallback when LLM fails entirely."""
    n = len(file_chunks)
    if n == 1:
        fc = file_chunks[0]
        name = fc['basename'].rsplit('.', 1)[0]
        if fc['deletions'] == 0:
            return f"feat({name}): add new file"
        elif fc['additions'] == 0:
            return f"chore({name}): remove file"
        else:
            return f"refactor({name}): update {fc['file_type']} logic"

    types = [fc['file_type'] for fc in file_chunks]
    dominant = max(set(types), key=types.count)
    return f"refactor({dominant}): update {n} files"


# ── orchestrator ───────────────────────────────────────────────────────────────

def _generate_commit_message(git_diff_output: str) -> str:
    """
    Full pipeline:
      1. Split diff by file
      2. Parallel chunk agents summarise each file
      3. Merge summaries
      4. Final agent writes commit message
      5. Fallback if LLM fails
    """
    file_chunks = _split_diff_by_file(git_diff_output)
    if not file_chunks:
        return "chore: minor changes"

    total_adds = sum(f['additions'] for f in file_chunks)
    total_dels = sum(f['deletions'] for f in file_chunks)
    print(f"📊 {len(file_chunks)} file(s) | +{total_adds} -{total_dels} lines")

    print("\n🤖 Step 1/3 — Running parallel chunk agents...")
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Already inside an event loop (FastAPI/uvicorn) — use a thread executor
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, _run_chunk_agents(file_chunks))
            summaries = future.result()
    else:
        summaries = asyncio.run(_run_chunk_agents(file_chunks))
        for s in summaries:
            print(f"   ✔ {s}")

    print("\n🔗 Step 2/3 — Merging summaries...")
    merged = _merge_summaries(summaries, file_chunks)

    print("✍  Step 3/3 — Final commit agent generating message...")
    message = _final_commit_agent(merged, len(file_chunks))

    if not message:
        print("⚠  LLM fallback triggered...")
        message = _fallback_message(file_chunks)

    return message


# ── langchain tool ─────────────────────────────────────────────────────────────

@tool
def git_commit(message: str = "auto") -> dict:
    """Create a git commit. If message is 'auto', uses parallel LLM agents to
    generate a meaningful commit message automatically and commits immediately.

    Args:
        message: Commit message, or 'auto' to generate one automatically.

    Returns:
        Dict with 'status' and 'message'.
    """
    if message.lower() == "auto":
        try:
            # Prefer staged, fall back to unstaged
            diff = subprocess.run(
                ['git', 'diff', '--cached'],
                capture_output=True, text=True, encoding='utf-8', errors='ignore'
            )
            if not diff.stdout.strip():
                print("🔍 No staged changes — checking unstaged...")
                diff = subprocess.run(
                    ['git', 'diff'],
                    capture_output=True, text=True, encoding='utf-8', errors='ignore'
                )

            raw_diff = diff.stdout.strip()
            if not raw_diff:
                return {
                    "status":  "error",
                    "message": "❌ No changes detected\n💡 Stage files with 'git add <files>' first",
                }

            print(f"🔍 Analysing {len(raw_diff):,} characters of git diff...\n")

            generated = _generate_commit_message(raw_diff)
            print(f"\n✅ Generated: {generated}")
            message = generated
        except Exception as e:
            return {"status": "error", "message": f"❌ Error during diff analysis: {e}"}

    # ── execute the commit ───────────────────────────────────────────────────
    result = subprocess.run(
        ['git', 'commit', '-m', message],
        capture_output=True, text=True, encoding='utf-8', errors='ignore'
    )

    if result.returncode == 0:
        return {"status": "success", "message": f"✅ Committed: {message}"}

    error_msg = result.stderr.strip() or result.stdout.strip() or "Commit failed"
    hint = ""
    if "nothing to commit" in error_msg.lower():
        hint = "\n💡 Stage files first: git add <files>"
    elif "please tell me who you are" in error_msg.lower():
        hint = "\n💡 Run: git config --global user.name/email"

    return {"status": "error", "message": f"❌ {error_msg}{hint}"}