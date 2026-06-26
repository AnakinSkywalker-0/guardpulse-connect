"""
vector_store.py
ChromaDB vector store using sentence-transformers for embeddings.
100% local — no API key needed for embedding.

FIX: Suppresses HuggingFace Hub unauthenticated request warning.
     The warning appears because sentence-transformers checks HF Hub on load.
     We don't need HF Hub — the model is cached locally after first download.
     Setting HF_HUB_DISABLE_TELEMETRY and TOKENIZERS_PARALLELISM env vars
     suppresses the noise without affecting functionality.
"""

import os
import warnings

# Suppress HuggingFace Hub warnings before importing sentence_transformers
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
# Suppress the unauthenticated requests warning
warnings.filterwarnings(
    "ignore",
    message=".*unauthenticated.*HF Hub.*",
    category=UserWarning,
)
# Suppress the BertModel LOAD REPORT / UNEXPECTED key warning
warnings.filterwarnings(
    "ignore",
    message=".*UNEXPECTED.*",
)
warnings.filterwarnings(
    "ignore",
    message=".*embeddings.position_ids.*",
)

import chromadb
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
from rich import print
from models import LegalChunk, RetrievedContext

load_dotenv()

CHROMA_DB_PATH       = os.getenv("CHROMA_DB_PATH", "./data/chroma_db")
COLLECTION_NAME      = "guardpulse_legal"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

_embedder: SentenceTransformer | None = None


def _get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        print("[cyan]Loading embedding model...[/cyan]")
        # Suppress sentence_transformers verbose load output
        import logging
        logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
        logging.getLogger("transformers").setLevel(logging.ERROR)
        _embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)
        print("[green]✓ Embedding model ready[/green]")
    return _embedder


def _get_collection():
    """Get or create the ChromaDB collection. Persists to disk automatically."""
    chroma = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    return chroma.get_or_create_collection(
        name     = COLLECTION_NAME,
        metadata = {"hnsw:space": "cosine"}
    )


def _embed_texts(texts: list[str]) -> list[list[float]]:
    print(f"  Embedding {len(texts)} texts locally...")
    vectors = _get_embedder().encode(
        texts,
        batch_size           = 32,
        show_progress_bar    = False,
        normalize_embeddings = True,
    )
    return vectors.tolist()


def _embed_query(question: str) -> list[float]:
    return _get_embedder().encode(
        [question],
        normalize_embeddings = True,
    )[0].tolist()


def store_chunks(chunks: list[LegalChunk]) -> int:
    """
    Embed and store chunks in ChromaDB.
    Skips already-stored chunks — safe to re-run.
    Returns count of new chunks added.
    """
    collection   = _get_collection()
    existing_ids = set(collection.get(include=[])["ids"])
    print(f"  ChromaDB already has {len(existing_ids)} vectors")

    new_chunks = [c for c in chunks if c.chunk_id not in existing_ids]
    if not new_chunks:
        print("  [green]All chunks already stored — skipping[/green]")
        return 0

    texts      = [c.text for c in new_chunks]
    embeddings = _embed_texts(texts)

    collection.add(
        ids       = [c.chunk_id for c in new_chunks],
        embeddings = embeddings,
        documents  = [c.text for c in new_chunks],
        metadatas  = [
            {
                "law_id":         c.law_id,
                "law_name":       c.law_name,
                "jurisdiction":   c.jurisdiction,
                "year":           c.year,
                "chunk_type":     c.chunk_type.value,
                "section_number": c.section_number or "",
                "section_title":  c.section_title  or "",
                "tags":           ",".join(c.tags),
                "source_url":     c.source_url,
            }
            for c in new_chunks
        ]
    )

    print(f"  [bold green]✓ Stored {len(new_chunks)} chunks in ChromaDB[/bold green]")
    return len(new_chunks)


def query(
    question: str,
    top_k:    int = 5,
    law_id:   str | None = None,
) -> list[RetrievedContext]:
    """
    Semantic search over legal knowledge base.
    law_id filters to a specific law e.g. "DPDP_2023".
    """
    collection   = _get_collection()
    print(f"  DB has {collection.count()} vectors")
    query_vector = _embed_query(question)
    where        = {"law_id": law_id} if law_id else None

    results = collection.query(
        query_embeddings = [query_vector],
        n_results        = top_k,
        where            = where,
        include          = ["documents", "metadatas", "distances"],
    )

    contexts = []
    for i in range(len(results["ids"][0])):
        meta = results["metadatas"][0][i]
        contexts.append(RetrievedContext(
            chunk_id       = results["ids"][0][i],
            law_id         = meta.get("law_id", ""),
            section_number = meta.get("section_number") or None,
            section_title  = meta.get("section_title")  or None,
            text           = results["documents"][0][i],
            score          = round(1 - results["distances"][0][i], 4),
            tags           = meta.get("tags", "").split(","),
        ))

    return contexts


def get_stats() -> dict:
    return {
        "total_vectors": _get_collection().count(),
        "collection":    COLLECTION_NAME,
        "db_path":       CHROMA_DB_PATH,
    }