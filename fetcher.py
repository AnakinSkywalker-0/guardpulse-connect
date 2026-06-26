"""
fetcher.py
Downloads DPDP Act 2023 (PDF) and EU AI Act (HTML) from public URLs.
Returns plain text + metadata dict ready for the chunker.
"""

import io
import time
import requests
# pyrefly: ignore [missing-import]
import pdfplumber
# pyrefly: ignore [missing-import]
import html2text
# pyrefly: ignore [missing-import]
from rich import print


# ── Legal document registry ───────────────────────────────────────────────────

LEGAL_SOURCES = {
    "DPDP_2023": {
        "name":         "Digital Personal Data Protection Act 2023",
        "url":          "https://www.indiacode.nic.in/bitstream/123456789/22037/1/a2023-22.pdf",
        "fallback":     "https://prsindia.org/files/bills_acts/acts_parliament/2023/Digital%20Personal%20Data%20Protection%20Act,%202023.pdf",
        "type":         "pdf",
        "jurisdiction": "IN",
        "year":         2023,
        "tags":         ["privacy", "PII", "consent", "india", "data_protection"]
    },
    "EU_AI_ACT_2024": {
    "name":         "EU Artificial Intelligence Act 2024",
    "url":          "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202401689",
    "fallback":     "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1689",
    "type":         "html",
    "jurisdiction": "EU",
    "year":         2024,
    "tags":         ["AI", "risk", "compliance", "EU", "prohibited_AI"]
    }
}


def _download(url: str, retries: int = 3) -> bytes:
    """Download raw bytes with retry logic."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    for attempt in range(1, retries + 1):
        try:
            print(f"  Attempt {attempt}: downloading from {url[:65]}...")
            r = requests.get(url, headers=headers, timeout=30)
            r.raise_for_status()
            return r.content
        except Exception as e:
            print(f"  [yellow]Attempt {attempt} failed: {e}[/yellow]")
            if attempt < retries:
                time.sleep(2)
    raise Exception(f"All {retries} attempts failed for {url}")


def _extract_pdf(raw: bytes) -> str:
    """Extract text from PDF bytes using pdfplumber."""
    pages = []
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        print(f"  PDF has {len(pdf.pages)} pages, extracting...")
        for i, page in enumerate(pdf.pages):
            try:
                text = page.extract_text()
                if text:
                    pages.append(text)
            except Exception as e:
                print(f"  [yellow]Skipping page {i+1}: {e}[/yellow]")
    return "\n\n".join(pages)


def _extract_html(raw: bytes) -> str:
    """Convert HTML to clean plain text."""
    converter = html2text.HTML2Text()
    converter.ignore_links  = True
    converter.ignore_images = True
    converter.body_width    = 0
    return converter.handle(raw.decode("utf-8", errors="replace"))


def fetch_document(law_id: str) -> dict | None:
    """
    MAIN FUNCTION — call this from other files.

    Pass a law_id like "DPDP_2023" or "EU_AI_ACT_2024".
    Returns a dict with text + metadata, or None on failure.
    """
    if law_id not in LEGAL_SOURCES:
        print(f"[red]Unknown law_id: {law_id}[/red]")
        return None

    source = LEGAL_SOURCES[law_id]
    print(f"\n[bold green]Fetching: {source['name']}[/bold green]")

    urls = [source["url"]]
    if source["fallback"]:
        urls.append(source["fallback"])

    for url in urls:
        try:
            raw  = _download(url)
            text = _extract_pdf(raw) if source["type"] == "pdf" else _extract_html(raw)

            min_chars = 50_000 if law_id == "EU_AI_ACT_2024" else 500
            if len(text.strip()) < min_chars:
                print(f"  [yellow]Too short ({len(text)} chars), trying fallback[/yellow]")
                continue

            print(f"  [bold green]✓ Success — {len(text):,} characters extracted[/bold green]")
            return {
                "law_id":       law_id,
                "law_name":     source["name"],
                "jurisdiction": source["jurisdiction"],
                "year":         source["year"],
                "tags":         source["tags"],
                "source_url":   url,
                "url_type":     source["type"],
                "text":         text
            }
        except Exception as e:
            print(f"  [red]Failed: {e}[/red]")
            continue

    print(f"[bold red]✗ Could not fetch {law_id}[/bold red]")
    return None


if __name__ == "__main__":
    doc = fetch_document("DPDP_2023")
    if doc:
        print(f"\nFirst 500 chars:\n{doc['text'][:500]}")