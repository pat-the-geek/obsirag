# Test: Runbook Incident Performance

import os
import subprocess
import pytest
from pathlib import Path

RUNBOOK_PATH = Path("docs/runbook_incident.md")

@pytest.mark.smoke
def test_runbook_exists_and_has_sections():
    assert RUNBOOK_PATH.exists(), "Le runbook incident doit exister."
    content = RUNBOOK_PATH.read_text(encoding="utf-8")
    for section in ["Détection", "Diagnostic", "Remédiation", "Documentation"]:
        assert section in content, f"Section manquante: {section}"

@pytest.mark.perf
def test_runbook_references_scripts():
    content = RUNBOOK_PATH.read_text(encoding="utf-8")
    for script in ["export_chroma_perf_report.py", "export_observability_weekly.py", "benchmark_baseline.py"]:
        assert script in content, f"Script non référencé: {script}"

@pytest.mark.perf
def test_runbook_references_feature_flags():
    content = RUNBOOK_PATH.read_text(encoding="utf-8")
    for flag in ["rag_backpressure_enabled", "rag_answer_cache_enabled"]:
        assert flag in content, f"Feature flag non référencé: {flag}"
