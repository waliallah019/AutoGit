"""Advanced Documentation Tool - AI-Powered PDF Documentation Generation"""
import asyncio
import subprocess
import os
import re
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from datetime import datetime

load_dotenv()

# ── constants ──────────────────────────────────────────────────────────────────
MAX_RAW_LINES_PER_CHUNK = 120   # split large files into sub-chunks at this size
MAX_CHUNK_CONTEXT       = 3000  # chars fed to each chunk agent
MAX_FINAL_CONTEXT       = 8000  # chars fed to the documentation agent

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
    """Split raw git diff into one dict per file with raw diff lines preserved."""
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
            # Keep +/- lines and hunk headers for agents
            if (line.startswith('+') and not line.startswith('+++')) or \
               (line.startswith('-') and not line.startswith('---')) or \
               line.startswith('@@'):
                current['raw_lines'].append(line)

    if current and not _should_ignore(current['filepath']):
        chunks.append(current)

    return chunks


def _sub_chunk(raw_lines: list, max_lines: int) -> list:
    """Split a file's diff lines into sub-chunks for very large files."""
    return [raw_lines[i:i + max_lines] for i in range(0, len(raw_lines), max_lines)]


def _make_llm(max_tokens: int = 300) -> ChatGroq:
    return ChatGroq(
        model="llama-3.1-8b-instant",
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=0.3,
        max_tokens=max_tokens,
    )


# ── parallel chunk agents ──────────────────────────────────────────────────────

async def _chunk_agent(file_chunk: dict, sub_lines: list, sub_idx: int, total_subs: int) -> str:
    """
    One async agent per file/sub-chunk.
    Returns a detailed plain-English description of what changed and why it matters.
    """
    raw_text = '\n'.join(sub_lines)
    if len(raw_text) > MAX_CHUNK_CONTEXT:
        raw_text = raw_text[:MAX_CHUNK_CONTEXT] + '\n[truncated]'

    sub_note = f" (part {sub_idx + 1}/{total_subs})" if total_subs > 1 else ""

    prompt = f"""You are a senior code reviewer writing documentation for a version control report.

FILE: {file_chunk['basename']}{sub_note}  |  type: {file_chunk['file_type']}  |  +{file_chunk['additions']} -{file_chunk['deletions']} lines

RAW DIFF LINES:
{raw_text}

Write 2-3 sentences describing:
1. WHAT specifically changed (name actual functions, variables, logic)
2. WHY this change was likely made (purpose, improvement, fix)

Rules:
- Be specific — use real names from the diff above
- Do NOT say "lines were added/removed" — describe the actual change
- Do NOT use bullet points
- Output ONLY the description, nothing else"""

    loop = asyncio.get_event_loop()
    llm  = _make_llm(max_tokens=200)

    try:
        response = await loop.run_in_executor(None, llm.invoke, prompt)
        summary  = response.content.strip()
        # Take first 3 sentences max to keep it tight
        sentences = [s.strip() for s in summary.replace('\n', ' ').split('.') if s.strip()]
        summary = '. '.join(sentences[:3]) + ('.' if sentences else '')
        return f"[{file_chunk['basename']}] {summary}"
    except Exception as e:
        return f"[{file_chunk['basename']}] +{file_chunk['additions']}/-{file_chunk['deletions']} lines changed in {file_chunk['file_type']} file."


async def _run_chunk_agents(file_chunks: list) -> list:
    """Launch all chunk agents in parallel via asyncio.gather."""
    tasks = []
    for fc in file_chunks:
        sub_chunks = _sub_chunk(fc['raw_lines'], MAX_RAW_LINES_PER_CHUNK)
        if not sub_chunks:
            sub_chunks = [[]]
        for idx, sub in enumerate(sub_chunks):
            tasks.append(_chunk_agent(fc, sub, idx, len(sub_chunks)))

    print(f"   ⚡ Launching {len(tasks)} parallel chunk agent(s)...")
    return list(await asyncio.gather(*tasks))


# ── documentation agent ────────────────────────────────────────────────────────

def _build_doc_context(summaries: list, file_chunks: list) -> str:
    """Build rich context string from chunk agent summaries for the doc agent."""
    total_adds = sum(f['additions'] for f in file_chunks)
    total_dels = sum(f['deletions'] for f in file_chunks)

    lines = [
        f"REPOSITORY CHANGES SUMMARY",
        f"Total files changed: {len(file_chunks)}",
        f"Total additions: +{total_adds}  Total deletions: -{total_dels}",
        f"",
        f"PER-FILE ANALYSIS (generated by parallel review agents):",
    ]
    for s in summaries:
        lines.append(f"  • {s}")

    result = '\n'.join(lines)
    if len(result) > MAX_FINAL_CONTEXT:
        result = result[:MAX_FINAL_CONTEXT] + '\n[truncated]'
    return result


def _generate_documentation_sections(doc_context: str) -> dict:
    """
    Single LLM call that reads all chunk summaries and writes all 5 doc sections.
    Returns a dict with keys: summary, changes, technical, impact, recommendations.
    """
    print('\n📋 Context sent to documentation agent:\n' + '─' * 60)
    print(doc_context[:600] + ('...' if len(doc_context) > 600 else ''))
    print('─' * 60 + '\n')

    prompt = f"""You are a technical documentation writer. Based on the per-file change analysis below, write a professional version control documentation report.

{doc_context}

Write EXACTLY these 5 sections. Use the section headers EXACTLY as shown. Each section must be 2-4 paragraphs of flowing prose (no bullet points, no markdown, no numbering).

===EXECUTIVE SUMMARY===
Explain the overall purpose and significance of this set of changes. What problem is being solved or what improvement is being made? What is the high-level impact on the system?

===DETAILED CHANGES===
For each file mentioned in the analysis above, write a paragraph explaining what specifically changed and why. Use actual function names, variable names, and logic from the analysis. Be concrete and specific.

===TECHNICAL IMPLEMENTATION===
Explain the technical approach taken. What patterns, architectures, or techniques were used? How do the changes work together technically? Reference specific functions, classes, or modules from the analysis.

===BUSINESS IMPACT===
Explain the practical value these changes deliver. How do they improve reliability, performance, maintainability, or user experience? What risks are reduced or capabilities added?

===FUTURE RECOMMENDATIONS===
Based on these specific changes, what follow-up work is recommended? What should be tested, monitored, or extended? Be specific to these actual changes, not generic advice.

CRITICAL: Write ONLY the 5 sections above. No preamble. No markdown. No bullet points. Start directly with ===EXECUTIVE SUMMARY==="""

    llm = _make_llm(max_tokens=2000)

    try:
        response = llm.invoke(prompt)
        if not response.content or len(response.content.strip()) < 200:
            return None
        return _parse_sections(response.content.strip())
    except Exception as e:
        print(f"⚠ Documentation agent error: {e}")
        return None


def _parse_sections(text: str) -> dict:
    """
    Parse the LLM output into 5 sections using the fixed delimiters ===SECTION===.
    This is reliable because we control the exact format the LLM was asked to use.
    """
    sections = {
        'summary':         '',
        'changes':         '',
        'technical':       '',
        'impact':          '',
        'recommendations': '',
    }

    # Map delimiter keywords to section keys
    delimiter_map = {
        'EXECUTIVE SUMMARY': 'summary',
        'DETAILED CHANGES':  'changes',
        'TECHNICAL IMPLEMENTATION': 'technical',
        'BUSINESS IMPACT':   'impact',
        'FUTURE RECOMMENDATIONS': 'recommendations',
    }

    # Split on ===...=== delimiters
    parts = re.split(r'===([^=]+)===', text)

    # parts[0] is text before first delimiter (discard)
    # parts[1], parts[3], parts[5]... are section names
    # parts[2], parts[4], parts[6]... are section content
    i = 1
    while i < len(parts) - 1:
        section_name = parts[i].strip().upper()
        content      = parts[i + 1].strip()

        for keyword, key in delimiter_map.items():
            if keyword in section_name:
                sections[key] = content
                break

        i += 2

    return sections


def _fallback_sections(summaries: list, file_chunks: list) -> dict:
    """Rule-based fallback when LLM fails entirely."""
    total_adds = sum(f['additions'] for f in file_chunks)
    total_dels = sum(f['deletions'] for f in file_chunks)
    n = len(file_chunks)

    changes_text = '\n\n'.join(summaries)

    return {
        'summary': (
            f"This update modifies {n} file(s) with {total_adds} lines added and "
            f"{total_dels} lines removed. The changes reflect targeted improvements "
            f"to the codebase as described in the per-file analysis below."
        ),
        'changes': changes_text,
        'technical': (
            f"The technical scope covers {n} file(s). "
            "Each file received targeted modifications as described in the change analysis. "
            "The changes collectively improve the structure and behaviour of the system."
        ),
        'impact': (
            "These changes improve code quality, reduce technical debt, and enhance "
            "system reliability. The modifications provide a more maintainable codebase "
            "for future development."
        ),
        'recommendations': (
            "Conduct thorough testing of all modified components. Review the changes "
            "in a code review session before merging. Monitor system behaviour after "
            "deployment to validate the improvements."
        ),
    }


# ── PDF builder ────────────────────────────────────────────────────────────────

def _build_pdf(
    output_path: str,
    repo_name: str,
    branch: str,
    diff_type: str,
    file_chunks: list,
    sections: dict,
) -> None:
    """Render the documentation sections into a professional PDF."""

    doc = SimpleDocTemplate(
        output_path, pagesize=letter,
        topMargin=0.75*inch, bottomMargin=0.75*inch,
        leftMargin=0.75*inch, rightMargin=0.75*inch,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=28, textColor=colors.HexColor('#1a237e'),
        spaceAfter=12, alignment=TA_CENTER, fontName='Helvetica-Bold',
    )
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16, textColor=colors.HexColor('#0d47a1'),
        spaceAfter=10, spaceBefore=16, fontName='Helvetica-Bold',
        backColor=colors.HexColor('#e3f2fd'), borderPadding=5,
    )
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['BodyText'],
        fontSize=11, leading=16, spaceAfter=10,
        alignment=TA_LEFT, fontName='Helvetica',
        textColor=colors.HexColor('#212121'),
    )

    story = []

    # ── Title page ──
    story.append(Spacer(1, 1.5*inch))
    story.append(Paragraph("Version Control", title_style))
    story.append(Paragraph("Documentation Report", title_style))
    story.append(Spacer(1, 0.5*inch))

    total_adds = sum(f['additions'] for f in file_chunks)
    total_dels = sum(f['deletions'] for f in file_chunks)

    info_data = [
        ['Repository:', repo_name],
        ['Branch:', branch],
        ['Analysis Type:', diff_type.title()],
        ['Generated:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
        ['Files Changed:', str(len(file_chunks))],
        ['Lines Added:', f"+{total_adds}"],
        ['Lines Deleted:', f"-{total_dels}"],
    ]
    info_table = Table(info_data, colWidths=[2*inch, 4*inch])
    info_table.setStyle(TableStyle([
        ('BACKGROUND',   (0, 0), (0, -1), colors.HexColor('#e3f2fd')),
        ('TEXTCOLOR',    (0, 0), (0, -1), colors.HexColor('#0d47a1')),
        ('FONTNAME',     (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME',     (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE',     (0, 0), (-1, -1), 11),
        ('ALIGN',        (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID',         (0, 0), (-1, -1), 0.5, colors.HexColor('#90caf9')),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
        ('TOPPADDING',   (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 8),
    ]))
    story.append(info_table)
    story.append(PageBreak())

    # ── Table of contents ──
    story.append(Paragraph("Table of Contents", heading_style))
    story.append(Spacer(1, 0.2*inch))
    for item in [
        "1. Executive Summary",
        "2. Files Changed",
        "3. Detailed Changes Analysis",
        "4. Technical Implementation",
        "5. Business Impact",
        "6. Future Recommendations",
    ]:
        story.append(Paragraph(f"   {item}", body_style))
    story.append(PageBreak())

    def _add_section(title: str, content: str, fallback: str = ""):
        story.append(Paragraph(title, heading_style))
        story.append(Spacer(1, 0.15*inch))
        text = content or fallback
        if text:
            for para in text.split('\n\n'):
                para = para.strip()
                if para:
                    safe = para.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    story.append(Paragraph(safe, body_style))
                    story.append(Spacer(1, 0.1*inch))
        story.append(Spacer(1, 0.3*inch))

    # ── 1. Executive Summary ──
    _add_section("1. Executive Summary", sections.get('summary', ''),
                 "This document provides a comprehensive overview of the recent changes made to the codebase.")

    # ── 2. Files Changed ──
    story.append(Paragraph("2. Files Changed", heading_style))
    story.append(Spacer(1, 0.15*inch))

    files_data = [['#', 'File', 'Type', 'Changes']]
    for idx, fc in enumerate(file_chunks, 1):
        files_data.append([
            str(idx),
            fc['filepath'],
            fc['file_type'],
            f"+{fc['additions']}/-{fc['deletions']}",
        ])

    files_table = Table(files_data, colWidths=[0.4*inch, 3.5*inch, 1.0*inch, 1.1*inch])
    files_table.setStyle(TableStyle([
        ('BACKGROUND',   (0, 0), (-1, 0), colors.HexColor('#0d47a1')),
        ('TEXTCOLOR',    (0, 0), (-1, 0), colors.white),
        ('FONTNAME',     (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',     (0, 0), (-1, 0), 10),
        ('ALIGN',        (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME',     (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE',     (0, 1), (-1, -1), 9),
        ('GRID',         (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
        ('TOPPADDING',   (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 6),
    ]))
    story.append(files_table)
    story.append(Spacer(1, 0.4*inch))

    # ── 3–6: LLM-generated sections ──
    _add_section("3. Detailed Changes Analysis", sections.get('changes', ''),
                 "Multiple files were updated. See the files table above for a summary.")

    _add_section("4. Technical Implementation", sections.get('technical', ''),
                 "The changes involve modifications to existing code structures and logic.")

    _add_section("5. Business Impact", sections.get('impact', ''),
                 "These changes improve the reliability and maintainability of the system.")

    _add_section("6. Future Recommendations", sections.get('recommendations', ''),
                 "Conduct thorough testing and code review before deploying these changes.")

    doc.build(story)


# ── langchain tool ─────────────────────────────────────────────────────────────

@tool
def generate_version_documentation() -> dict:
    """Generate detailed PDF documentation of current changes based on git diff analysis.
    Uses parallel LLM agents to analyse each changed file, then produces a professional
    version control documentation PDF with AI-generated analysis.

    Returns:
        Dictionary with status, message, and path to generated PDF.
    """
    output_file = "version_control_doc.pdf"

    try:
        # ── verify git repo ──
        check = subprocess.run(
            ['git', 'rev-parse', '--git-dir'],
            capture_output=True, text=True, encoding='utf-8', errors='ignore',
        )
        if check.returncode != 0:
            return {"status": "error", "message": "Not a git repository. Run 'git init' first."}

        # ── get diff ──
        diff = subprocess.run(
            ['git', 'diff', '--cached'],
            capture_output=True, text=True, encoding='utf-8', errors='ignore',
        )
        raw_diff  = diff.stdout.strip()
        diff_type = "staged changes"

        if not raw_diff:
            diff = subprocess.run(
                ['git', 'diff'],
                capture_output=True, text=True, encoding='utf-8', errors='ignore',
            )
            raw_diff  = diff.stdout.strip()
            diff_type = "unstaged changes"

        if not raw_diff:
            return {
                "status": "error",
                "message": "No changes detected. Make changes or run 'git add <files>' first.",
            }

        # ── repo metadata ──
        repo_r = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True, text=True, encoding='utf-8', errors='ignore',
        )
        repo_name = os.path.basename(repo_r.stdout.strip()) if repo_r.returncode == 0 else "Repository"

        branch_r = subprocess.run(
            ['git', 'branch', '--show-current'],
            capture_output=True, text=True, encoding='utf-8', errors='ignore',
        )
        branch = branch_r.stdout.strip() or "main"

        # ── step 1: split diff by file ──
        print(f"\n🔍 Analysing {len(raw_diff):,} characters of git diff...")
        file_chunks = _split_diff_by_file(raw_diff)

        if not file_chunks:
            return {"status": "error", "message": "No relevant file changes found after filtering."}

        total_adds = sum(f['additions'] for f in file_chunks)
        total_dels = sum(f['deletions'] for f in file_chunks)
        print(f"📊 {len(file_chunks)} file(s) | +{total_adds} -{total_dels} lines\n")

        # ── step 2: parallel chunk agents ──
        print("🤖 Step 1/3 — Running parallel chunk agents (one per file)...")
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

        print("\n   Chunk agent results:")
        for s in summaries:
            print(f"   ✔ {s}")

        # ── step 3: documentation agent ──
        print("\n📝 Step 2/3 — Building documentation context...")
        doc_context = _build_doc_context(summaries, file_chunks)

        print("✍  Step 3/3 — Documentation agent generating all sections...")
        sections = _generate_documentation_sections(doc_context)

        if not sections:
            print("⚠  LLM failed — using fallback documentation...")
            sections = _fallback_sections(summaries, file_chunks)

        # Verify no section is empty — fall back per-section if needed
        fallback = _fallback_sections(summaries, file_chunks)
        for key in sections:
            if not sections[key] or len(sections[key].strip()) < 50:
                print(f"⚠  Section '{key}' empty — using fallback for that section")
                sections[key] = fallback[key]

        # ── step 4: render PDF ──
        print("\n📄 Rendering PDF...")
        pdf_path = os.path.abspath(output_file)
        _build_pdf(pdf_path, repo_name, branch, diff_type, file_chunks, sections)

        print(f"✅ PDF saved: {pdf_path}\n")
        return {
            "status":   "success",
            "message":  f"Documentation generated successfully!\nFile: {pdf_path}",
            "pdf_path": pdf_path,
        }

    except ImportError:
        return {"status": "error", "message": "reportlab not installed. Run: pip install reportlab"}
    except Exception as e:
        return {"status": "error", "message": f"Failed to generate documentation: {e}"}