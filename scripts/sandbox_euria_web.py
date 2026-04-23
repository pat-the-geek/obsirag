#!/usr/bin/env python3
"""
Sandbox — diagnostique l'accès web d'Euria étape par étape.

Usage :
    .venv/bin/python scripts/sandbox_euria_web.py "votre question"
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Ajoute la racine du projet au PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

# Charge le .env
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")


QUESTION = sys.argv[1] if len(sys.argv) > 1 else "Quel est le prix du MacBook Air M4 en 2025 ?"


# ─── Étape 0 : config Euria ───────────────────────────────────────────────────
print("\n" + "═" * 70)
print("ÉTAPE 0 — Config Euria")
print("═" * 70)

from src.config import settings
euria_url = (settings.euria_url or "").strip()
euria_bearer = (settings.euria_bearer or "").strip()
print(f"  EURIA_URL    : {euria_url[:60] + '...' if len(euria_url) > 60 else euria_url or '(vide)'}")
print(f"  EURIA_BEARER : {'***' + euria_bearer[-4:] if len(euria_bearer) > 4 else '(vide)'}")

if not euria_url or not euria_bearer:
    print("\n  ❌ EURIA non configurée — arrêt du diagnostic")
    sys.exit(1)


# ─── Étape 1 : keywordize ─────────────────────────────────────────────────────
print("\n" + "═" * 70)
print("ÉTAPE 1 — Keywordize la question")
print("═" * 70)
print(f"  Question     : {QUESTION!r}")

from src.ai.web_search import _keywordize_query
search_query = _keywordize_query(QUESTION)
print(f"  Requête DDG  : {search_query!r}")


# ─── Étape 2 : DDG instant answer ─────────────────────────────────────────────
print("\n" + "═" * 70)
print("ÉTAPE 2 — DDG Instant Answer")
print("═" * 70)

from src.ai.web_search import _ddg_instant_answer_search
t0 = time.perf_counter()
instant = _ddg_instant_answer_search(search_query, max_results=3)
print(f"  Durée        : {time.perf_counter() - t0:.2f}s")
print(f"  Résultats    : {len(instant)}")
for i, r in enumerate(instant, 1):
    print(f"  [{i}] {r.get('title', '?')} — {r.get('href', '?')[:60]}")
    if r.get("body"):
        print(f"       {r['body'][:120]}...")


# ─── Étape 3 : DDG texte ──────────────────────────────────────────────────────
print("\n" + "═" * 70)
print("ÉTAPE 3 — DDG Recherche texte")
print("═" * 70)

from src.ai.web_search import _ddg_search
t0 = time.perf_counter()
ddg_results = _ddg_search(search_query, max_results=5)
print(f"  Durée        : {time.perf_counter() - t0:.2f}s")
print(f"  Résultats    : {len(ddg_results)}")
for i, r in enumerate(ddg_results, 1):
    print(f"  [{i}] {r.get('title', '?')} — {r.get('href', '?')[:60]}")
    if r.get("body"):
        print(f"       {r['body'][:120]}...")


# ─── Étape 4 : merge ──────────────────────────────────────────────────────────
print("\n" + "═" * 70)
print("ÉTAPE 4 — Merge des résultats")
print("═" * 70)

from src.ai.web_search import _merge_search_results
web_results = _merge_search_results(instant, ddg_results, max_results=5)
print(f"  Total après merge : {len(web_results)}")
for i, r in enumerate(web_results, 1):
    body_preview = (r.get("body") or "")[:100]
    print(f"  [{i}] {r.get('title', '?')[:50]}")
    print(f"       URL  : {r.get('href', '?')[:60]}")
    print(f"       Body : {body_preview}{'...' if len(body_preview) == 100 else ''}")


# ─── Étape 5 : construction du prompt ─────────────────────────────────────────
print("\n" + "═" * 70)
print("ÉTAPE 5 — Construction du prompt Euria")
print("═" * 70)

if web_results:
    snippets = "\n\n".join(
        f"**{r.get('title', '')}** ({r.get('href', '')})\n{r.get('body', '')}"
        for r in web_results
        if r.get("body")
    )
    user_content = (
        f"Résultats de recherche web récents :\n\n{snippets}\n\n"
        f"Question : {QUESTION}"
    )
    print(f"  Snippets injectés : {len([r for r in web_results if r.get('body')])}")
    print(f"  Longueur user_content : {len(user_content)} chars")
    print(f"\n  --- Début user_content ---")
    print(user_content[:600] + ("..." if len(user_content) > 600 else ""))
    print(f"  --- Fin user_content ---")
else:
    user_content = QUESTION
    print(f"  ⚠️  Aucun snippet DDG — prompt sans contexte web")

messages = [
    {
        "role": "system",
        "content": (
            "Tu réponds UNIQUEMENT et EXCLUSIVEMENT en français, quelle que soit la langue des sources ou de la question. "
            "Même si les résultats de recherche web sont en anglais, ta réponse doit être entièrement rédigée en français. "
            "Utilise du Markdown valide et propre. "
            "Des résultats de recherche web récents te sont fournis comme contexte. "
            "Appuie-toi dessus pour répondre avec précision et cite les sources entre crochets. "
            "Priorité absolue aux informations du contexte web sur tes données d'entraînement."
        ),
    },
    {"role": "user", "content": user_content},
]


# ─── Étape 6 : appel Euria ────────────────────────────────────────────────────
print("\n" + "═" * 70)
print("ÉTAPE 6 — Appel Euria (streaming)")
print("═" * 70)

from src.ai.euria_client import EuriaClient
try:
    client = EuriaClient(url=euria_url, bearer=euria_bearer)
except ValueError as e:
    print(f"  ❌ Init EuriaClient : {e}")
    sys.exit(1)

print(f"  Modèle : {client._model}")
print(f"  URL    : {client._url[:60]}...")
print(f"  Appel streaming en cours...\n")

t0 = time.perf_counter()
collected = []
try:
    for chunk in client.stream(
        messages,
        temperature=0.3,
        max_tokens=2048,
        operation="sandbox-web-test",
        enable_web_search=False,  # on injecte nous-mêmes, pas besoin du flag natif
    ):
        collected.append(chunk)
        print(chunk, end="", flush=True)
except Exception as e:
    print(f"\n  ❌ Erreur streaming : {e}")
    sys.exit(1)

answer = "".join(collected)
elapsed = time.perf_counter() - t0

print(f"\n\n{'═' * 70}")
print(f"RÉSULTAT")
print(f"{'═' * 70}")
print(f"  Durée totale : {elapsed:.1f}s")
print(f"  Longueur     : {len(answer)} chars / ~{len(answer.split())} mots")
print(f"  Tokens/s     : ~{len(answer.split()) / elapsed:.1f} mots/s")

# ─── Étape 7 : analyse ────────────────────────────────────────────────────────
print(f"\n{'═' * 70}")
print(f"DIAGNOSTIC")
print(f"{'═' * 70}")

web_result_count = len(web_results)
answer_lower = answer.lower()

# Vérifie si la réponse cite des sources issues des snippets
cited_sources = []
for r in web_results:
    title = (r.get("title") or "").lower()
    href  = (r.get("href") or "").lower()
    if any(word in answer_lower for word in title.split() if len(word) > 4):
        cited_sources.append(r.get("title", "?"))

print(f"  DDG snippets récupérés : {web_result_count}")
print(f"  Sources citées dans la réponse : {len(cited_sources)}")
for s in cited_sources:
    print(f"    ✅ {s}")
if not cited_sources and web_result_count > 0:
    print(f"    ⚠️  Aucune source DDG apparemment citée dans la réponse")

# Détecte si la réponse utilise les infos web
training_phrases = ["selon mes informations", "d'après mes données", "je ne dispose pas", "mes connaissances"]
web_phrases = ["selon", "d'après", "source", "résultat", "site", "page", "article"]
uses_web_phrases = sum(1 for p in web_phrases if p in answer_lower)
uses_training = any(p in answer_lower for p in training_phrases)

if uses_training:
    print(f"\n  ⚠️  La réponse mentionne des formules de données d'entraînement")
else:
    print(f"\n  ✅ Pas de formule 'données d'entraînement' détectée")

print(f"\n  Conclusion : {'✅ Contexte web injecté utilisé' if web_result_count > 0 else '❌ Aucun contexte web disponible — réponse depuis données entraînement uniquement'}")
