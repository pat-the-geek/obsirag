"""
Tests unitaires — scripts/canary_validation.py (PERF-16)
Toutes les fonctions pures testées sans LLM ni store vecteurs réels.
"""
from __future__ import annotations

import pytest
from scripts.canary_validation import (
    PhaseResult,
    QueryOutcome,
    _build_report,
    _PHASE_BUDGETS,
)


# ---------------------------------------------------------------------------
# PhaseResult — calculs statistiques
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPhaseResult:
    def _make_result(self, phase: int, latencies: list[float],
                     n_errors: int = 0, n_sentinels: int = 0) -> PhaseResult:
        r = PhaseResult(phase=phase, n=len(latencies),
                        n_errors=n_errors, n_sentinels=n_sentinels,
                        latencies=latencies)
        return r

    def test_p50_single_value(self):
        r = self._make_result(1, [5.0])
        assert r.p50_s == 5.0

    def test_p50_multiple_values(self):
        r = self._make_result(1, [1.0, 3.0, 5.0, 7.0, 9.0])
        assert r.p50_s == 5.0

    def test_p95_at_budget_boundary(self):
        # 10 valeurs, k = max(1, int(10*0.95)) = 9, index 8 → valeur 9.0
        latencies = [float(i) for i in range(1, 11)]
        r = self._make_result(1, latencies)
        assert r.p95_s == 9.0

    def test_empty_latencies(self):
        r = self._make_result(1, [])
        assert r.p50_s == 0.0
        assert r.p95_s == 0.0

    def test_error_rate(self):
        r = self._make_result(1, [1.0, 2.0, 3.0], n_errors=1)
        assert abs(r.error_rate - 1 / 3) < 1e-9

    def test_sentinel_rate(self):
        # 4 requêtes, 1 erreur → 3 valides ; 2 sentinels sur 3 valides
        r = self._make_result(1, [1.0] * 4, n_errors=1, n_sentinels=2)
        assert abs(r.sentinel_rate - 2 / 3) < 1e-9


# ---------------------------------------------------------------------------
# PhaseResult.go_nogo()
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGoNogo:
    def _fast_phase(self, phase: int) -> PhaseResult:
        """Résultat sous tous les seuils → GO attendu."""
        budget = _PHASE_BUDGETS[phase]
        latencies = [budget["p95_s"] * 0.5] * 4  # P95 à 50 % du budget
        return PhaseResult(phase=phase, n=4, n_errors=0, n_sentinels=0, latencies=latencies)

    def test_go_when_all_within_budget(self):
        for phase in [1, 2, 3]:
            r = self._fast_phase(phase)
            go, reasons = r.go_nogo()
            assert go, f"Phase {phase} devrait être GO — raisons : {reasons}"
            assert reasons == []

    def test_nogo_on_p95_exceeded(self):
        budget = _PHASE_BUDGETS[1]["p95_s"]
        r = PhaseResult(phase=1, n=2, latencies=[budget * 2.0, budget * 2.0])
        go, reasons = r.go_nogo()
        assert not go
        assert any("P95" in r for r in reasons)

    def test_nogo_on_error_rate(self):
        r = PhaseResult(phase=1, n=1, n_errors=1, latencies=[1.0])
        go, reasons = r.go_nogo()
        assert not go
        assert any("erreur" in r for r in reasons)

    def test_nogo_on_sentinel_rate(self):
        budget = _PHASE_BUDGETS[1]
        # On met toutes les latences bien en dessous du budget
        n = 10
        latencies = [budget["p95_s"] * 0.1] * n
        # On force un taux sentinel > seuil
        n_sentinels = int(budget["max_sentinel_rate"] * n) + 2
        r = PhaseResult(phase=1, n=n, n_errors=0, n_sentinels=n_sentinels, latencies=latencies)
        go, reasons = r.go_nogo()
        assert not go
        assert any("sentinel" in r for r in reasons)

    def test_multiple_failures_listed(self):
        budget = _PHASE_BUDGETS[1]
        r = PhaseResult(
            phase=1, n=2, n_errors=1, n_sentinels=2,
            latencies=[budget["p95_s"] * 3.0, budget["p95_s"] * 3.0],
        )
        go, reasons = r.go_nogo()
        assert not go
        assert len(reasons) >= 2


# ---------------------------------------------------------------------------
# _build_report()
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBuildReport:
    def _make_go_result(self, phase: int) -> PhaseResult:
        budget = _PHASE_BUDGETS[phase]
        latencies = [budget["p95_s"] * 0.3] * 2
        return PhaseResult(phase=phase, n=2, latencies=latencies,
                           outcomes=[
                               QueryOutcome(phase=phase, query="Q1", total_s=latencies[0]),
                               QueryOutcome(phase=phase, query="Q2", total_s=latencies[1]),
                           ])

    def test_overall_go_when_all_phases_pass(self):
        results = [self._make_go_result(p) for p in [1, 2, 3]]
        report = _build_report(results, "2026-04-13T00:00:00+00:00")
        assert report["overall_go"] is True

    def test_overall_nogo_when_any_phase_fails(self):
        go1 = self._make_go_result(1)
        fail2 = PhaseResult(phase=2, n=1, n_errors=1, latencies=[999.0],
                            outcomes=[QueryOutcome(phase=2, query="Q", total_s=999.0, error="boom")])
        results = [go1, fail2]
        report = _build_report(results, "2026-04-13T00:00:00+00:00")
        assert report["overall_go"] is False

    def test_report_contains_feature_flags(self):
        results = [self._make_go_result(1)]
        report = _build_report(results, "2026-04-13T00:00:00+00:00")
        assert "feature_flags" in report
        assert "rag_backpressure_enabled" in report["feature_flags"]
        assert "rag_answer_cache_enabled" in report["feature_flags"]

    def test_report_has_finished_at(self):
        results = [self._make_go_result(1)]
        report = _build_report(results, "2026-04-13T00:00:00+00:00")
        assert "finished_at" in report
        assert report["finished_at"] != ""

    def test_phase_outcomes_are_included(self):
        results = [self._make_go_result(1)]
        report = _build_report(results, "2026-04-13T00:00:00+00:00")
        assert len(report["phases"]) == 1
        assert len(report["phases"][0]["outcomes"]) == 2
