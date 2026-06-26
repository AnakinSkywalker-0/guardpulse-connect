"""
chunker.py
Splits legal documents by actual Section/Clause structure.
NOT by word count — that destroys legal meaning.

Strategy:
  1. Detect section headers (Indian & EU format)
  2. De-duplicate TOC matches vs real sections
  3. Merge tiny sections with the next one
  4. Split oversized sections at clause markers
"""

import re
from models import LegalChunk, ChunkType
from rich import print

MAX_CHUNK_CHARS = 3200   # ~800 tokens
OVERLAP_CHARS   = 200
MIN_CHUNK_CHARS = 200    # sections smaller than this get merged forward


def _detect_chunk_type(text: str, section_num: str | None) -> ChunkType:
    upper = text.upper()
    if not section_num:
        if any(w in upper for w in ["WHEREAS", "PREAMBLE", "BE IT ENACTED"]):
            return ChunkType.PREAMBLE
        if any(w in upper for w in ["SCHEDULE", "ANNEX", "APPENDIX"]):
            return ChunkType.SCHEDULE
    if len(re.findall(r'"\w[\w\s]+"\s+means\b', text)) >= 2:
        return ChunkType.DEFINITION
    if section_num:
        return ChunkType.SECTION
    return ChunkType.UNKNOWN


def _is_toc(text: str) -> bool:
    """Returns True if the block looks like a table of contents."""
    if "ARRANGEMENT OF SECTIONS" in text.upper():
        return True
    toc_lines   = len(re.findall(r'\.{2,}\s*\d+\s*$', text, re.MULTILINE))
    total_lines = len(text.strip().splitlines())
    return total_lines > 0 and (toc_lines / total_lines) > 0.3


def _find_boundaries(text: str) -> list[tuple]:
    """
    Finds all section headers in the document.
    De-duplicates by section number — keeps the LAST match
    (real content) and discards the first (TOC reference).
    """
    found = []

    # Indian Act format: "6. Consent." or "12A. Title"
    for m in re.compile(r"^(\d+[A-Z]?)\.\s+([A-Z][^\n]{3,80})", re.MULTILINE).finditer(text):
        found.append((m.start(), m.group(1), m.group(2).strip()))

    # EU format: "Article 5 — Title"
    for m in re.compile(r"^Article\s+(\d+[a-z]?)\s*[—–-]?\s*([A-Z][^\n]{0,80})?",
                        re.MULTILINE | re.IGNORECASE).finditer(text):
        num   = "Art." + m.group(1)
        title = m.group(2).strip() if m.group(2) else f"Article {m.group(1)}"
        found.append((m.start(), num, title))

    found.sort(key=lambda x: x[0])

    # Keep only last occurrence of each section number
    seen: dict[str, tuple] = {}
    for item in found:
        seen[item[1]] = item

    return sorted(seen.values(), key=lambda x: x[0])


def _split_large(text: str) -> list[str]:
    """Split a section that exceeds MAX_CHUNK_CHARS at clause markers."""
    parts  = re.compile(r"\n(?=\s*\(\d+\)|\s*\([a-z]\))").split(text)
    result = []
    buffer = ""

    for part in parts:
        candidate = (buffer + "\n" + part).strip() if buffer else part.strip()
        if len(candidate) <= MAX_CHUNK_CHARS:
            buffer = candidate
        else:
            if buffer:
                result.append(buffer)
            if len(part) > MAX_CHUNK_CHARS:
                for i in range(0, len(part), MAX_CHUNK_CHARS - OVERLAP_CHARS):
                    result.append(part[i: i + MAX_CHUNK_CHARS])
            else:
                buffer = part.strip()

    if buffer:
        result.append(buffer)
    return [r for r in result if r.strip()]


def chunk_document(doc: dict) -> list[LegalChunk]:
    """
    MAIN FUNCTION — always returns a list, never None.

    Takes the dict from fetcher.fetch_document()
    and returns LegalChunk objects ready for ChromaDB.
    """
    text   = doc["text"]
    law_id = doc["law_id"]

    print(f"\n[bold]Chunking: {doc['law_name']}[/bold]")
    print(f"  Total text: {len(text):,} chars")

    boundaries = _find_boundaries(text)
    print(f"  Found {len(boundaries)} unique section boundaries")

    chunks = []   # always initialised, always returned

    if not boundaries:
        print("  [yellow]No sections found — using fixed-size fallback[/yellow]")
        for i in range(0, len(text), MAX_CHUNK_CHARS - OVERLAP_CHARS):
            piece = text[i: i + MAX_CHUNK_CHARS]
            chunks.append(LegalChunk(
                chunk_id=f"{law_id}_fallback_{len(chunks):04d}",
                law_id=law_id, law_name=doc["law_name"],
                jurisdiction=doc["jurisdiction"], year=doc["year"],
                chunk_type=ChunkType.UNKNOWN, text=piece.strip(),
                token_count=len(piece) // 4, tags=doc["tags"],
                source_url=doc["source_url"]
            ))
        return chunks

    # Build raw section blocks
    raw = []
    for i, (start, num, title) in enumerate(boundaries):
        end  = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
        body = text[start:end].strip()
        if not body:
            continue
        if _is_toc(body):
            print(f"  [yellow]Skipping TOC ({len(body):,} chars)[/yellow]")
            continue
        raw.append((num, title, body))

    # Merge tiny sections forward
    merged = []
    buf_num, buf_title, buf_text = None, None, ""

    for num, title, body in raw:
        if buf_text:
            if len(buf_text) < MIN_CHUNK_CHARS:
                buf_text = buf_text + "\n\n" + body
                continue
            else:
                merged.append((buf_num, buf_title, buf_text))
        buf_num, buf_title, buf_text = num, title, body

    if buf_text:
        merged.append((buf_num, buf_title, buf_text))

    print(f"  After merging small sections: {len(merged)} sections")

    # Build final LegalChunk objects
    for num, title, body in merged:
        ctype = _detect_chunk_type(body, num)

        if len(body) <= MAX_CHUNK_CHARS:
            chunks.append(LegalChunk(
                chunk_id=f"{law_id}_s{num}_c0",
                law_id=law_id, law_name=doc["law_name"],
                jurisdiction=doc["jurisdiction"], year=doc["year"],
                chunk_type=ctype, section_number=num, section_title=title,
                text=body, token_count=len(body) // 4,
                tags=doc["tags"], source_url=doc["source_url"]
            ))
        else:
            for idx, sub in enumerate(_split_large(body)):
                chunks.append(LegalChunk(
                    chunk_id=f"{law_id}_s{num}_c{idx}",
                    law_id=law_id, law_name=doc["law_name"],
                    jurisdiction=doc["jurisdiction"], year=doc["year"],
                    chunk_type=ChunkType.CLAUSE if idx > 0 else ctype,
                    section_number=num, section_title=title,
                    text=sub, token_count=len(sub) // 4,
                    tags=doc["tags"], source_url=doc["source_url"]
                ))

    print(f"  [bold green]✓ Created {len(chunks)} chunks[/bold green]")
    return chunks


if __name__ == "__main__":
    from fetcher import fetch_document
    doc    = fetch_document("DPDP_2023")
    chunks = chunk_document(doc)
    for c in chunks[:3]:
        print(f"\n[cyan]── {c.chunk_id} ──[/cyan]")
        print(f"Section : {c.section_number} — {c.section_title}")
        print(f"Type    : {c.chunk_type.value}  |  Tokens: {c.token_count}")
        print(f"Preview : {c.text[:200]}")
