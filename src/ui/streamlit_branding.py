from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import streamlit


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sync_streamlit_favicon() -> bool:
    source = Path(__file__).parent / "static" / "favicon-32x32.png"
    target = Path(streamlit.__file__).resolve().parent / "static" / "favicon.png"

    if not source.exists() or not target.exists():
        return False

    if _sha256(source) == _sha256(target):
        return False

    shutil.copyfile(source, target)
    return True


if __name__ == "__main__":
    updated = sync_streamlit_favicon()
    print("streamlit favicon synchronized" if updated else "streamlit favicon already up to date")