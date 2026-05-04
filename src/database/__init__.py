"""
Factory de la couche vecteurs.

Utilise settings.vector_backend pour choisir l'implémentation :
  - "chroma"  → ChromaStore  (défaut, HNSW persisté)
  - "lance"   → LanceStore   (LanceDB, multi-process safe)

Tous les consommateurs qui importaient directement ChromaStore peuvent
continuer à le faire, ou utiliser make_vector_store() pour respecter le
paramètre de config.
"""
from __future__ import annotations

from src.config import settings


def make_vector_store():
    """Retourne une instance du store vecteurs configuré."""
    backend = (settings.vector_backend or "chroma").lower().strip()
    if backend == "lance":
        from src.database.lance_store import LanceStore
        return LanceStore()
    from src.database.chroma_store import ChromaStore
    return ChromaStore()
