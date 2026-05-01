"""
Logging professionnel avec loguru.
- Console colorée
- Fichier rotatif (10 MB, rétention 30 jours, compression zip)
- Fichier d'erreurs séparé
- Suivi de la consommation de tokens IA (méthode dédiée)
"""
import sys
import json
import threading
from collections import deque
from pathlib import Path
from datetime import datetime, timezone
from loguru import logger

from src.storage.safe_read import read_json_file


_TOKEN_STATS_LOCK = threading.RLock()
_LOG_BUFFER_LOCK = threading.RLock()
_LOG_BUFFER_MAX = 2000
_LOG_BUFFER: deque[dict] = deque(maxlen=_LOG_BUFFER_MAX)


def _capture_log_record(message) -> None:
    """Capture une copie des logs en mémoire pour l'API /system/logs."""
    record = message.record
    with _LOG_BUFFER_LOCK:
        _LOG_BUFFER.append(
            {
                "timestamp": record["time"].astimezone(timezone.utc).isoformat(),
                "level": str(record["level"].name),
                "name": str(record.get("name") or ""),
                "line": int(record.get("line") or 0),
                "message": str(record.get("message") or ""),
            }
        )


def get_log_buffer() -> list[dict]:
    """Retourne une copie du buffer de logs mémoire."""
    with _LOG_BUFFER_LOCK:
        return list(_LOG_BUFFER)


def configure_logging(log_level: str = "INFO", log_dir: str = "/app/logs") -> None:
    logger.remove()

    fmt_console = (
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{line}</cyan> — "
        "<level>{message}</level>"
    )
    fmt_file = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
        "{level: <8} | "
        "{name}:{function}:{line} — "
        "{message}"
    )

    logger.add(sys.stdout, format=fmt_console, level=log_level, colorize=True)

    # Sink mémoire utilisé par l'endpoint API /api/v1/system/logs.
    logger.add(_capture_log_record, level="DEBUG")

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    logger.add(
        log_path / "obsirag.log",
        format=fmt_file,
        level="DEBUG",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
    )

    logger.add(
        log_path / "errors.log",
        format=fmt_file + "\n{exception}",
        level="ERROR",
        rotation="5 MB",
        retention="60 days",
        encoding="utf-8",
    )

    logger.add(
        log_path / "tokens.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {message}",
        level="INFO",
        filter=lambda r: r["extra"].get("token_log") is True,
        rotation="5 MB",
        retention="90 days",
        encoding="utf-8",
    )


def log_token_usage(
    operation: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    token_stats_file: Path,
) -> None:
    """Enregistre la consommation de tokens dans le log dédié et met à jour les stats cumulées."""
    total = prompt_tokens + completion_tokens

    logger.bind(token_log=True).info(
        f"op={operation} model={model} "
        f"prompt={prompt_tokens} completion={completion_tokens} total={total}"
    )

    # Mise à jour du fichier de stats JSON
    with _TOKEN_STATS_LOCK:
        token_stats_file.parent.mkdir(parents=True, exist_ok=True)

        stats: dict = {}
        if token_stats_file.exists():
            stats = read_json_file(token_stats_file, default={})

        today = datetime.now(timezone.utc).date().isoformat()
        day_stats = stats.setdefault(today, {})
        op_stats = day_stats.setdefault(operation, {"prompt": 0, "completion": 0, "calls": 0})
        op_stats["prompt"] += prompt_tokens
        op_stats["completion"] += completion_tokens
        op_stats["calls"] += 1

        cumul = stats.setdefault("cumulative", {"prompt": 0, "completion": 0, "calls": 0})
        cumul["prompt"] += prompt_tokens
        cumul["completion"] += completion_tokens
        cumul["calls"] += 1

        try:
            tmp_file = token_stats_file.with_suffix(f"{token_stats_file.suffix}.tmp")
            tmp_file.write_text(
                json.dumps(stats, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp_file.replace(token_stats_file)
        except Exception as exc:
            logger.warning(f"Impossible d'écrire les stats de tokens : {exc}")
