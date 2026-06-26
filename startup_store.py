"""
startup_store.py — Phase 3.

A second ChromaDB collection ("guardpulse_startups"), separate from the
legal knowledge base in vector_store.py. Stores registered startup
profiles with embeddings of their description for semantic matching.

Uses the same embedding model as vector_store.py for consistency, but
keeps its own collection so startup search never mixes with law search.
"""

import os
# pyrefly: ignore [missing-import]
import chromadb
# pyrefly: ignore [missing-import]
from sentence_transformers import SentenceTransformer
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
from rich import print
from models import StartupProfile

load_dotenv()

CHROMA_DB_PATH       = os.getenv("CHROMA_DB_PATH", "./data/chroma_db")
STARTUP_COLLECTION   = "guardpulse_startups"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

_embedder: SentenceTransformer | None = None


def _get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        print("[cyan]Loading embedding model...[/cyan]")
        _embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)
        print("[green]✓ Embedding model ready[/green]")
    return _embedder


def _get_collection():
    chroma = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    return chroma.get_or_create_collection(
        name=STARTUP_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )


def store_startup(profile: StartupProfile) -> None:
    """
    Embed the startup's description and store/update its profile.
    Overwrites if startup_id already exists (re-registration updates score).
    """
    collection = _get_collection()
    embedder   = _get_embedder()

    vector = embedder.encode(
        [profile.description],
        normalize_embeddings=True,
    )[0].tolist()

    collection.upsert(
        ids        = [profile.startup_id],
        embeddings = [vector],
        documents  = [profile.description],
        metadatas  = [{
            "startup_name":     profile.startup_name,
            "category":         profile.category,
            "capabilities":     ",".join(profile.capabilities),
            "guardpulse_score": profile.guardpulse_score,
            "badge":            profile.badge.value,
            "legal_score":      profile.legal_score,
            "tech_score":       profile.tech_score,
            "document_audited": profile.document_audited,
            "registered_at":    profile.registered_at,
        }],
    )
    print(f"  [bold green]✓ Stored startup profile: {profile.startup_name}[/bold green]")


def search_startups(semantic_query: str, top_k: int = 10) -> list[tuple[StartupProfile, float]]:
    """
    Semantic search over registered startups.
    Returns list of (StartupProfile, similarity_score) tuples.
    """
    collection = _get_collection()
    if collection.count() == 0:
        return []

    embedder     = _get_embedder()
    query_vector = embedder.encode([semantic_query], normalize_embeddings=True)[0].tolist()

    results = collection.query(
        query_embeddings = [query_vector],
        n_results        = min(top_k, collection.count()),
        include          = ["documents", "metadatas", "distances"],
    )

    matches = []
    for i in range(len(results["ids"][0])):
        meta  = results["metadatas"][0][i]
        score = round(1 - results["distances"][0][i], 4)

        profile = StartupProfile(
            startup_id        = results["ids"][0][i],
            startup_name       = meta.get("startup_name", "Unknown"),
            description         = results["documents"][0][i],
            category            = meta.get("category", "general"),
            capabilities         = meta.get("capabilities", "").split(",") if meta.get("capabilities") else [],
            guardpulse_score     = float(meta.get("guardpulse_score", 0.0)),
            badge                = meta.get("badge", "NOT_READY"),
            legal_score          = float(meta.get("legal_score", 0.0)),
            tech_score           = float(meta.get("tech_score", 0.0)),
            document_audited     = meta.get("document_audited", ""),
            registered_at        = meta.get("registered_at", ""),
        )
        matches.append((profile, score))

    return matches


def list_all_startups() -> list[StartupProfile]:
    """Return every registered startup — used by `main.py startups` command."""
    collection = _get_collection()
    if collection.count() == 0:
        return []

    data    = collection.get(include=["documents", "metadatas"])
    results = []
    for i, sid in enumerate(data["ids"]):
        meta = data["metadatas"][i]
        results.append(StartupProfile(
            startup_id        = sid,
            startup_name       = meta.get("startup_name", "Unknown"),
            description         = data["documents"][i],
            category            = meta.get("category", "general"),
            capabilities         = meta.get("capabilities", "").split(",") if meta.get("capabilities") else [],
            guardpulse_score     = float(meta.get("guardpulse_score", 0.0)),
            badge                = meta.get("badge", "NOT_READY"),
            legal_score          = float(meta.get("legal_score", 0.0)),
            tech_score           = float(meta.get("tech_score", 0.0)),
            document_audited     = meta.get("document_audited", ""),
            registered_at        = meta.get("registered_at", ""),
        ))
    return results


def get_stats() -> dict:
    return {
        "total_startups": _get_collection().count(),
        "collection":     STARTUP_COLLECTION,
        "db_path":        CHROMA_DB_PATH,
    }