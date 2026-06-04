from backend.analyze import (
    is_perf_regression,
    group_failure_signatures,
    compare_runs,
)


def test_is_perf_regression_true():
    assert is_perf_regression(100, 125, threshold=0.2)


def test_is_perf_regression_false():
    assert not is_perf_regression(100, 110, threshold=0.2)


def test_group_failure_signatures_ignores_passes():
    results = {
        ("dma", "t1", 1): {
            "status": "FAIL",
            "failure_type": "ASSERTION_FAILED",
            "assertion_name": "valid_ready_protocol",
        },
        ("dma", "t2", 2): {
            "status": "FAIL",
            "failure_type": "ASSERTION_FAILED",
            "assertion_name": "valid_ready_protocol",
        },
        ("dma", "t3", 3): {
            "status": "PASS",
            "failure_type": "none",
            "assertion_name": "none",
        },
    }

    groups = group_failure_signatures(results)

    assert groups == [("ASSERTION_FAILED:valid_ready_protocol", 2)]


def test_compare_runs_detects_categories():
    baseline_results = {
        ("dma", "new_fail", 1): {
            "suite": "dma",
            "test_name": "new_fail",
            "seed": 1,
            "status": "PASS",
            "failure_type": "none",
            "assertion_name": "none",
            "cycles": 100,
        },
        ("dma", "fixed", 2): {
            "suite": "dma",
            "test_name": "fixed",
            "seed": 2,
            "status": "FAIL",
            "failure_type": "ASSERTION_FAILED",
            "assertion_name": "fifo_no_overflow",
            "cycles": 100,
        },
        ("dma", "still_fail", 3): {
            "suite": "dma",
            "test_name": "still_fail",
            "seed": 3,
            "status": "FAIL",
            "failure_type": "ASSERTION_FAILED",
            "assertion_name": "packet_ordering",
            "cycles": 100,
        },
        ("dma", "slow", 4): {
            "suite": "dma",
            "test_name": "slow",
            "seed": 4,
            "status": "PASS",
            "failure_type": "none",
            "assertion_name": "none",
            "cycles": 100,
        },
    }

    current_results = {
        ("dma", "new_fail", 1): {
            "suite": "dma",
            "test_name": "new_fail",
            "seed": 1,
            "status": "FAIL",
            "failure_type": "ASSERTION_FAILED",
            "assertion_name": "valid_ready_protocol",
            "cycles": 100,
        },
        ("dma", "fixed", 2): {
            "suite": "dma",
            "test_name": "fixed",
            "seed": 2,
            "status": "PASS",
            "failure_type": "none",
            "assertion_name": "none",
            "cycles": 100,
        },
        ("dma", "still_fail", 3): {
            "suite": "dma",
            "test_name": "still_fail",
            "seed": 3,
            "status": "FAIL",
            "failure_type": "ASSERTION_FAILED",
            "assertion_name": "packet_ordering",
            "cycles": 100,
        },
        ("dma", "slow", 4): {
            "suite": "dma",
            "test_name": "slow",
            "seed": 4,
            "status": "PASS",
            "failure_type": "none",
            "assertion_name": "none",
            "cycles": 130,
        },
    }

    comparison = compare_runs(baseline_results, current_results)

    assert len(comparison["new_failures"]) == 1
    assert len(comparison["fixed_tests"]) == 1
    assert len(comparison["still_failing"]) == 1
    assert len(comparison["perf_regressions"]) == 1
    assert len(comparison["infra_failures"]) == 0