from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), extra="ignore")

    # Coffre Obsidian (lecture, + écriture dans obsirag/insights et obsirag/synthesis)
    vault_path: str = "/vault"

    # Données système ObsiRAG — volume Docker (HORS coffre, pas de sync iCloud)
    app_data_dir: str = "/app/data"

    # MLX-LM (génération locale Apple Silicon — remplace Ollama)
    mlx_chat_model: str = "mlx-community/Qwen2.5-7B-Instruct-4bit"

    # Ollama (conservé pour compatibilité ascendante / fallback éventuel)
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_chat_model: str = ""
    ollama_embed_model: Optional[str] = None
    ollama_context_size: int = 4096  # n_ctx du modèle chargé dans Ollama

    # Embeddings locaux
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"

    # NER
    ner_model: str = "xx_ent_wiki_sm"

    # WUDD.ai — entités NER officielles
    wuddai_entities_url: str = "http://100.72.122.51:5050"

    # ChromaDB
    chroma_collection: str = "vault_chunks"

    # Logging
    log_level: str = "INFO"
    log_dir: str = "/app/logs"

    # Auto-apprentissage
    autolearn_enabled: bool = True
    autolearn_interval_minutes: int = 60
    autolearn_max_notes_per_run: int = 5
    autolearn_lookback_hours: int = 24
    autolearn_fullscan_per_run: int = 3   # notes non traitées à couvrir par cycle
    autolearn_min_reprocess_days: int = 7  # ne pas retraiter une note avant N jours
    autolearn_synapse_per_run: int = 2    # paires synaptiques à découvrir par cycle
    autolearn_synapse_threshold: float = 0.65  # similarité cosine minimale
    autolearn_active_hour_start: int = 8   # heure de début (locale) des cycles auto
    autolearn_active_hour_end: int = 22    # heure de fin (locale, exclusive) des cycles auto
    autolearn_bulk_max_notes: int = 20     # nb max de notes par passe bulk initiale (0 = illimité)

    # RAG / Chunking
    chunk_size_words: int = 350
    chunk_overlap_words: int = 50
    search_top_k: int = 8
    max_context_chunks: int = 6
    max_context_chars: int = 6000
    max_chunk_chars: int = 800

    # ---- Propriétés dérivées ----

    @property
    def vault(self) -> Path:
        return Path(self.vault_path)

    obsidian_vault_name: str = ""  # ex: "Coffre-de-Pat" — à définir dans .env

    @property
    def obsidian_vault(self) -> str:
        """Nom du coffre tel qu'Obsidian le connaît."""
        return self.obsidian_vault_name or Path(self.vault_path).name

    # -- Données système (volume Docker, hors coffre) --

    @property
    def data_dir(self) -> Path:
        """Répertoire système ObsiRAG — volume Docker, invisible pour Obsidian."""
        return Path(self.app_data_dir)

    @property
    def chroma_persist_dir(self) -> str:
        return str(self.data_dir / "chroma")

    @property
    def index_state_file(self) -> Path:
        return self.data_dir / "index_state.json"

    @property
    def token_stats_file(self) -> Path:
        return self.data_dir / "stats" / "token_usage.json"

    @property
    def processing_times_file(self) -> Path:
        """Historique glissant des durées réelles de traitement par note (secondes)."""
        return self.data_dir / "stats" / "processing_times.json"

    @property
    def queries_file(self) -> Path:
        return self.data_dir / "queries" / "queries.jsonl"

    @property
    def processed_notes_file(self) -> Path:
        return self.data_dir / "autolearn" / "processed_notes.json"

    @property
    def bulk_done_flag_file(self) -> Path:
        return self.data_dir / "autolearn" / "bulk_done.flag"

    @property
    def processing_status_file(self) -> Path:
        return self.data_dir / "autolearn" / "processing_status.json"

    @property
    def graph_dir(self) -> Path:
        return self.data_dir / "graph"

    # -- Données Markdown dans le coffre (visibles dans Obsidian) --

    @property
    def vault_obsirag_dir(self) -> Path:
        """Dossier ObsiRAG dans le coffre — contient uniquement du Markdown."""
        return self.vault / "obsirag"

    @property
    def insights_dir(self) -> Path:
        """Artefacts de connaissance auto-générés — lisibles dans Obsidian."""
        return self.vault_obsirag_dir / "insights"

    @property
    def synthesis_dir(self) -> Path:
        """Synthèses hebdomadaires — lisibles dans Obsidian."""
        return self.vault_obsirag_dir / "synthesis"

    @property
    def synapses_dir(self) -> Path:
        """Connexions implicites découvertes entre notes — lisibles dans Obsidian."""
        return self.vault_obsirag_dir / "synapses"

    @property
    def conversations_dir(self) -> Path:
        """Conversations sauvegardées depuis le chat — lisibles dans Obsidian."""
        return self.vault_obsirag_dir / "conversations"

    @property
    def synapse_index_file(self) -> Path:
        """Index des paires déjà traitées pour éviter les doublons."""
        return self.data_dir / "autolearn" / "synapse_index.json"

    # -- Compatibilité (alias) --
    @property
    def knowledge_dir(self) -> Path:
        return self.insights_dir


settings = Settings()
