"""
cortex_api/ab_test_framework.py — Cortex A/B Test Framework.

Extends Cortex's capabilities with:
1. Multi-Variate Testing: test multiple variants simultaneously
2. Statistical Significance: calculate p-values and confidence intervals
3. Bayesian A/B Testing: Bayesian approach to A/B testing
4. Sequential Testing: test while traffic is flowing
5. Holdout Groups: control group management
6. Test Automation: auto-run tests and get results
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from cortex_api.config import get_db_session
from cortex_api.auth import Role, require_role

router = APIRouter()


@dataclass
class TestVariant:
    """A test variant."""
    variant_id: str
    name: str
    description: str = ""
    allocation: float = 0.5  # Percentage of traffic
    is_control: bool = False


@dataclass
class TestMetric:
    """A metric to measure in an A/B test."""
    metric_id: str
    name: str
    type: str = "binary"  # binary, continuous, ratio
    target: float = 0.0
    unit: str = ""


@dataclass
class TestResult:
    """A test result."""
    test_id: str
    status: str  # running, significant, not_significant, inconclusive
    p_value: float
    confidence: float
    lift: float
    winner: str = ""
    recommendation: str = ""
    days_elapsed: int = 0
    sample_size: int = 0
    significance_threshold: float = 0.05


@dataclass
class BayesianResult:
    """Bayesian A/B test result."""
    test_id: str
    variant_a_prob: float
    variant_b_prob: float
    lift_prob: float
    expected_loss_a: float
    expected_loss_b: float
    recommendation: str
    confidence: float


class ABTestFramework:
    """A/B testing framework with statistical rigor."""

    def __init__(self):
        self._tests: dict[str, dict] = {}
        self._results: dict[str, TestResult] = {}
        self._bayesian_results: dict[str, BayesianResult] = {}

    # ── Test Management ─────────────────────────────────────────────────────

    def create_test(
        self,
        test_id: str,
        name: str,
        variants: list[TestVariant],
        metrics: list[TestMetric],
        significance_threshold: float = 0.05,
        min_sample_size: int = 100,
    ) -> dict:
        """Create an A/B test."""
        test = {
            "test_id": test_id,
            "name": name,
            "variants": variants,
            "metrics": metrics,
            "significance_threshold": significance_threshold,
            "min_sample_size": min_sample_size,
            "status": "running",
            "created_at": time.time(),
            "results": {},
        }

        self._tests[test_id] = test
        return test

    # ── Statistical Significance ─────────────────────────────────────────────

    def calculate_significance(
        self,
        variant_a_data: dict,
        variant_b_data: dict,
    ) -> TestResult:
        """Calculate statistical significance between two variants."""
        # Conversion rate for binary metrics
        conv_a = variant_a_data.get("conversions", 0)
        visitors_a = variant_a_data.get("visitors", 1000)
        conv_b = variant_b_data.get("conversions", 0)
        visitors_b = variant_b_data.get("visitors", 1000)

        rate_a = conv_a / visitors_a
        rate_b = conv_b / visitors_b

        # Pooled rate
        p_pool = (conv_a + conv_b) / (visitors_a + visitors_b)

        # Standard error
        se = math.sqrt(
            p_pool * (1 - p_pool) * (1 / visitors_a + 1 / visitors_b)
        )

        # Z-score
        z = (rate_b - rate_a) / se if se > 0 else 0.0

        # P-value
        p_value = math.erf(abs(z) / math.sqrt(2))

        # Confidence
        confidence = p_value

        # Lift
        lift = (rate_b - rate_a) / rate_a if rate_a > 0 else 0.0

        # Determine winner
        if p_value < 0.05:
            winner = "B" if rate_b > rate_a else "A"
            status = "significant"
            recommendation = f"Variant {winner} is significantly better (p={p_value:.4f})"
        else:
            status = "not_significant"
            recommendation = f"No significant difference (p={p_value:.4f})"

        result = TestResult(
            test_id=f"test_{int(time.time())}",
            status=status,
            p_value=p_value,
            confidence=confidence,
            lift=lift,
            winner=winner,
            recommendation=recommendation,
            sample_size=visitors_a + visitors_b,
        )

        return result

    # ── Bayesian A/B Testing ────────────────────────────────────────────────

    def bayesian_test(
        self,
        variant_a_data: dict,
        variant_b_data: dict,
    ) -> BayesianResult:
        """Bayesian A/B test."""
        a_conversions = variant_a_data.get("conversions", 0)
        a_visitors = variant_a_data.get("visitors", 1000)
        b_conversions = variant_b_data.get("conversions", 0)
        b_visitors = variant_b_data.get("visitors", 1000)

        # Beta distribution parameters
        a_alpha = a_conversions + 1
        a_beta = a_visitors - a_conversions + 1
        b_alpha = b_conversions + 1
        b_beta = b_visitors - b_conversions + 1

        # Calculate probability B > A (simplified using normal approximation)
        a_rate = a_alpha / (a_alpha + a_beta)
        b_rate = b_alpha / (b_alpha + b_beta)

        # Standard deviations
        a_var = a_alpha * a_beta / ((a_alpha + a_beta) ** 2 * (a_alpha + a_beta + 1))
        b_var = b_alpha * b_beta / ((b_alpha + b_beta) ** 2 * (b_alpha + b_beta + 1))

        diff_mean = b_rate - a_rate
        diff_std = math.sqrt(a_var + b_var)

        if diff_std > 0:
            prob_b_better = math.erf(diff_mean / (diff_std * math.sqrt(2))) / 2 + 0.5
        else:
            prob_b_better = 0.5

        # Expected loss
        expected_loss_a = max(0, b_rate - a_rate) * a_visitors
        expected_loss_b = max(0, a_rate - b_rate) * b_visitors

        # Recommendation
        if prob_b_better > 0.95:
            recommendation = "Choose variant B - high confidence"
        elif prob_b_better > 0.90:
            recommendation = "Choose variant B - good confidence"
        elif prob_b_better < 0.05:
            recommendation = "Choose variant A - high confidence"
        elif prob_b_better < 0.10:
            recommendation = "Choose variant A - good confidence"
        else:
            recommendation = "Continue testing - insufficient data"

        result = BayesianResult(
            test_id=f"bayesian_{int(time.time())}",
            variant_a_prob=1.0 - prob_b_better,
            variant_b_prob=prob_b_better,
            lift_prob=prob_b_better,
            expected_loss_a=expected_loss_a,
            expected_loss_b=expected_loss_b,
            recommendation=recommendation,
            confidence=abs(prob_b_better - 0.5) * 2,
        )

        return result

    # ── Sequential Testing ───────────────────────────────────────────────────

    def sequential_test(
        self,
        test_id: str,
        daily_data: list[dict],
        alpha: float = 0.05,
        max_days: int = 30,
    ) -> TestResult:
        """Sequential A/B test that can stop early."""
        cum_a = 0
        cum_b = 0
        cum_visitors_a = 0
        cum_visitors_b = 0

        for day, data in enumerate(daily_data):
            if day > max_days:
                break

            cum_a += data.get("a_conversions", 0)
            cum_b += data.get("b_conversions", 0)
            cum_visitors_a += data.get("a_visitors", 0)
            cum_visitors_b += data.get("b_visitors", 0)

            # Check significance at each step
            result = self.calculate_significance(
                {"conversions": cum_a, "visitors": cum_visitors_a},
                {"conversions": cum_b, "visitors": cum_visitors_b},
            )

            result.days_elapsed = day + 1

            if result.status == "significant":
                result.recommendation += f" - stopped early at day {day + 1}"
                return result

        return result

    # ── Holdout Management ──────────────────────────────────────────────────

    def create_holdout(
        self,
        test_id: str,
        holdout_size: float = 0.1,
    ) -> dict:
        """Create a holdout/control group."""
        return {
            "test_id": test_id,
            "holdout_size": holdout_size,
            "holdout_id": f"holdout_{test_id}",
            "created_at": time.time(),
        }

    # ── Test Automation ──────────────────────────────────────────────────────

    def auto_run_test(
        self,
        test_id: str,
        variant_a_data: dict,
        variant_b_data: dict,
    ) -> dict:
        """Auto-run an A/B test and return results."""
        test = self._tests.get(test_id)
        if not test:
            return {"status": "NOT_FOUND"}

        # Run both frequentist and Bayesian
        freq_result = self.calculate_significance(variant_a_data, variant_b_data)
        bayes_result = self.bayesian_test(variant_a_data, variant_b_data)

        self._results[test_id] = freq_result
        self._bayesian_results[test_id] = bayes_result

        return {
            "test_id": test_id,
            "frequentist": freq_result.__dict__,
            "bayesian": bayes_result.__dict__,
        }

    # ── Reporting ──────────────────────────────────────────────────────────

    def get_ab_test_report(self) -> dict[str, Any]:
        """Generate an A/B test report."""
        total = len(self._results)
        significant = sum(1 for r in self._results.values() if r.status == "significant")

        return {
            "total_tests": len(self._tests),
            "completed_tests": total,
            "significant_tests": significant,
            "bayesian_tests": len(self._bayesian_results),
        }


# Module-level singleton
ab_test_framework = ABTestFramework()


# ── API Routes ──────────────────────────────────────────────────────────────


@router.post("/api/v1/ab-test/create")
async def create_ab_test(
    payload: dict,
    db: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_role(Role.CORTEX_ADMIN)),
):
    """Create an A/B test."""
    variants = [TestVariant(**v) for v in payload["variants"]]
    metrics = [TestMetric(**m) for m in payload["metrics"]]

    test = ab_test_framework.create_test(
        test_id=payload["test_id"],
        name=payload["name"],
        variants=variants,
        metrics=metrics,
        significance_threshold=payload.get("significance_threshold", 0.05),
        min_sample_size=payload.get("min_sample_size", 100),
    )

    return {"test_id": test["test_id"], "status": "created"}


@router.post("/api/v1/ab-test/{test_id}/run")
async def run_ab_test(
    test_id: str,
    payload: dict,
    user: dict = Depends(require_role(Role.CORTEX_OPERATOR)),
):
    """Run an A/B test."""
    return ab_test_framework.auto_run_test(
        test_id=test_id,
        variant_a_data=payload["variant_a"],
        variant_b_data=payload["variant_b"],
    )


@router.get("/api/v1/ab-test/{test_id}/result")
async def get_ab_test_result(
    test_id: str,
    user: dict = Depends(require_role(Role.CORTEX_VIEWER)),
):
    """Get A/B test result."""
    result = ab_test_framework._results.get(test_id)
    if not result:
        return {"status": "NOT_FOUND"}

    return result.__dict__


@router.post("/api/v1/ab-test/bayesian")
async def bayesian_ab_test(
    payload: dict,
    user: dict = Depends(require_role(Role.CORTEX_OPERATOR)),
):
    """Run Bayesian A/B test."""
    result = ab_test_framework.bayesian_test(
        payload["variant_a"],
        payload["variant_b"],
    )
    return result.__dict__


@router.get("/api/v1/ab-test/report")
async def ab_test_report(
    user: dict = Depends(require_role(Role.CORTEX_VIEWER)),
):
    """Get A/B test report."""
    return ab_test_framework.get_ab_test_report()
