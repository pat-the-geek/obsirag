from __future__ import annotations

import subprocess

from scripts import diagnose_chroma_crash


def test_classify_probe_marks_negative_return_code_as_native_crash() -> None:
    completed = subprocess.CompletedProcess(args=["python"], returncode=-11, stdout="", stderr="boom")

    result = diagnose_chroma_crash._classify_probe(completed, "chroma_get_metadatas")

    assert result["nativeCrash"] is True
    assert result["signal"] == "SIGSEGV"


def test_build_summary_reports_first_failure_and_first_native_crash() -> None:
    results = [
        {"step": "embed", "returncode": 0, "stdout": "", "stderr": "", "nativeCrash": False},
        {"step": "chroma_get_limit_only", "returncode": -10, "stdout": "", "stderr": "", "nativeCrash": True, "signal": "SIGBUS"},
        {"step": "search_semantic", "returncode": -11, "stdout": "", "stderr": "", "nativeCrash": True, "signal": "SIGSEGV"},
    ]

    summary = diagnose_chroma_crash._build_summary(results)

    assert summary["ok"] is False
    assert summary["firstFailure"] == {
        "step": "chroma_get_limit_only",
        "returncode": -10,
        "signal": "SIGBUS",
    }
    assert summary["firstNativeCrash"] == {
        "step": "chroma_get_limit_only",
        "returncode": -10,
        "signal": "SIGBUS",
    }