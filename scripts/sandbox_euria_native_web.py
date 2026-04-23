#!/usr/bin/env python3
"""
Sandbox — test du flag enable_web_search natif d'Euria vs DDG injection.

Usage :
    .venv/bin/python scripts/sandbox_euria_native_web.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from src.config import settings
from src.ai.euria_client import EuriaClient

QUESTION = "Quel est le prix actuel du MacBook Air M4 13 pouces en France en avril 2025 ?"

euria_url = (settings.euria_url or "").strip()
euria_bearer = (settings.euria_bearer or "").strip()

if not euria_url or not euria_bearer:
    print("❌ EURIA non configurée")
    sys.exit(1)

client = EuriaClient(url=euria_url, bearer=euria_bearer)


def run_test(label: str, messages: list, enable_web_search: bool, max_tokens: int = 2048) -> tuple[str, float]:
    print(f"\n{'═'*70}")
    print(f"TEST : {label}")
    print(f"  enable_web_search={enable_web_search}  max_tokens={max_tokens}")
    print(f"  Question : {QUESTION}")
    print(f"{'─'*70}")
    t0 = time.perf_counter()
    parts = []
    try:
        for chunk in client.stream(
            messages,
            temperature=0.3,
            max_tokens=max_tokens,
            operation=f"sandbox-{label}",
            enable_web_search=enable_web_search,
        ):
            parts.append(chunk)
            print(chunk, end="", flush=True)
    except Exception as e:
        print(f"\n❌ Erreur : {e}")
        return "", time.perf_counter() - t0
    elapsed = time.perf_counter() - t0
    answer = "".join(parts)
    print(f"\n\n  ⏱  Durée : {elapsed:.1f}s  |  {len(answer)} chars  |  ~{len(answer.split())/elapsed:.1f} mots/s")
    return answer, elapsed


# ─── Messages communs ─────────────────────────────────────────────────────────
SYSTEM_NOTHINK = {
    "role": "system",
    "content": (
        "/no_think\n"
        "Tu réponds UNIQUEMENT en français. "
        "Si tu as accès à une recherche web, utilise-la pour répondre avec des informations récentes et précises. "
        "Cite les sources entre crochets."
    ),
}
SYSTEM_BASIC = {
    "role": "system",
    "content": "Tu réponds UNIQUEMENT en français. Utilise la recherche web si disponible.",
}
USER_MSG = {"role": "user", "content": QUESTION}


# ─── Test 1 : enable_web_search=True + /no_think ──────────────────────────────
answer1, t1 = run_test(
    "enable_web_search=True + /no_think",
    messages=[SYSTEM_NOTHINK, USER_MSG],
    enable_web_search=True,
    max_tokens=2048,
)

# ─── Test 2 : enable_web_search=True sans /no_think ──────────────────────────
answer2, t2 = run_test(
    "enable_web_search=True sans /no_think",
    messages=[SYSTEM_BASIC, USER_MSG],
    enable_web_search=True,
    max_tokens=2048,
)

# ─── Test 3 : enable_web_search=False (contrôle) ─────────────────────────────
answer3, t3 = run_test(
    "enable_web_search=False (données entraînement)",
    messages=[SYSTEM_NOTHINK, USER_MSG],
    enable_web_search=False,
    max_tokens=1024,
)

# ─── Résumé ───────────────────────────────────────────────────────────────────
print(f"\n{'═'*70}")
print("RÉSUMÉ COMPARATIF")
print(f"{'═'*70}")

def score_freshness(text: str) -> str:
    fresh_markers = ["2025", "mars 2025", "m4", "prix", "€", "apple store", "1"]
    stale_markers = ["je ne dispose pas", "données d'entraînement", "ma date limite", "je n'ai pas accès"]
    f = sum(1 for m in fresh_markers if m.lower() in text.lower())
    s = sum(1 for m in stale_markers if m.lower() in text.lower())
    if s > 0:
        return "⚠️  données entraînement détectées"
    if f >= 3:
        return "✅ info récentes (web actif)"
    return "❓ ambigu"

for label, answer, elapsed in [
    ("enable_web_search=True + /no_think", answer1, t1),
    ("enable_web_search=True sans /no_think", answer2, t2),
    ("enable_web_search=False (contrôle)", answer3, t3),
]:
    print(f"\n  [{label}]")
    print(f"    Durée   : {elapsed:.1f}s")
    print(f"    Qualité : {score_freshness(answer)}")
    if answer:
        print(f"    Extrait : {answer[:180].replace(chr(10),' ')}...")
