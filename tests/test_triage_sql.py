import sqlite3

from backend import db
from backend.triage_sql import (
    compare_run_to_many,
    current_failures,
    current_failures_by_worker,
    failed_test_vcds,
    fetch_comparison_rows,
    filter_values,
    new_failures,
    query_comparison,
    summarize_comparison,
    top_failure_signatures,
    worst_perf_regressions,
)


def make_fixture_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)

    cur = conn.cursor()
    cur.execute(
        "INSERT INTO runs (run_name, commit_hash, created_at) VALUES (?, ?, ?)",
        ("run_001", "abc123", "2026-06-21T00:00:00"),
    )
    baseline_id = cur.lastrowid
    cur.execute(
        "INSERT INTO runs (run_name, commit_hash, created_at) VALUES (?, ?, ?)",
        ("run_002", "def456", "2026-06-21T00:01:00"),
    )
    current_id = cur.lastrowid
    cur.execute(
        "INSERT INTO runs (run_name, commit_hash, created_at) VALUES (?, ?, ?)",
        ("run_003", "ghi789", "2026-06-21T00:02:00"),
    )
    third_id = cur.lastrowid

    baseline_rows = [
        ("dma", "new_fail", 1, "worker-1", "PASS", None, None, None, 100, 100, 0.8),
        ("dma", "fixed", 2, "worker-1", "FAIL", "ASSERTION_FAILED", "fifo_no_overflow", "waves/fixed.vcd", 100, 100, 0.8),
        ("dma", "still_fail", 3, "worker-2", "FAIL", "ASSERTION_FAILED", "packet_ordering", "waves/still.vcd", 100, 100, 0.8),
        ("cache", "slow", 4, "worker-3", "PASS", None, None, None, 100, 100, 0.8),
        ("cache", "fast", 5, "worker-3", "PASS", None, None, None, 100, 100, 0.8),
        ("noc", "infra", 6, "worker-4", "PASS", None, None, None, 100, 100, 0.8),
    ]
    current_rows = [
        ("dma", "new_fail", 1, "worker-1", "FAIL", "ASSERTION_FAILED", "valid_ready_protocol", "waves/new.vcd", 130, 100, 0.8),
        ("dma", "fixed", 2, "worker-1", "PASS", None, None, None, 100, 100, 0.8),
        ("dma", "still_fail", 3, "worker-2", "FAIL", "ASSERTION_FAILED", "packet_ordering", "waves/still.vcd", 100, 100, 0.8),
        ("cache", "slow", 4, "worker-3", "PASS", None, None, None, 130, 100, 0.8),
        ("cache", "fast", 5, "worker-3", "PASS", None, None, None, 75, 100, 0.8),
        ("noc", "infra", 6, "worker-4", "FAIL", "INFRA_FAILURE", "sim_timeout", "waves/infra.vcd", 100, 100, 0.8),
    ]
    third_rows = [
        ("dma", "new_fail", 1, "worker-1", "PASS", None, None, None, 100, 100, 0.8),
        ("dma", "fixed", 2, "worker-1", "PASS", None, None, None, 100, 100, 0.8),
        ("dma", "still_fail", 3, "worker-2", "FAIL", "ASSERTION_FAILED", "packet_ordering", "waves/still_3.vcd", 125, 100, 0.8),
        ("cache", "slow", 4, "worker-3", "PASS", None, None, None, 150, 100, 0.8),
        ("cache", "fast", 5, "worker-3", "PASS", None, None, None, 90, 100, 0.8),
        ("noc", "infra", 6, "worker-4", "PASS", None, None, None, 100, 100, 0.8),
    ]

    insert_results(conn, baseline_id, baseline_rows)
    insert_results(conn, current_id, current_rows)
    insert_results(conn, third_id, third_rows)
    conn.commit()
    return conn, baseline_id, current_id, third_id


def insert_results(conn, run_id, rows):
    for row in rows:
        (
            suite,
            test_name,
            seed,
            worker_id,
            status,
            failure_type,
            assertion_name,
            artifact_path,
            cycles,
            expected_cycles,
            utilization,
        ) = row

        conn.execute(
            """
            INSERT OR IGNORE INTO test_cases (suite, test_name, seed, test_family)
            VALUES (?, ?, ?, ?)
            """,
            (suite, test_name, seed, test_name.rsplit("_", 1)[0]),
        )
        test_case_id = conn.execute(
            """
            SELECT id
            FROM test_cases
            WHERE suite = ?
              AND test_name = ?
              AND seed = ?
            """,
            (suite, test_name, seed),
        ).fetchone()["id"]

        failure_signature_id = None
        if status == "FAIL":
            conn.execute(
                """
                INSERT OR IGNORE INTO failure_signatures (failure_type, assertion_name)
                VALUES (?, ?)
                """,
                (failure_type, assertion_name),
            )
            failure_signature_id = conn.execute(
                """
                SELECT id
                FROM failure_signatures
                WHERE failure_type = ?
                  AND assertion_name = ?
                """,
                (failure_type, assertion_name),
            ).fetchone()["id"]

        conn.execute(
            """
            INSERT INTO test_results (
                run_id,
                test_case_id,
                worker_name,
                status,
                failure_signature_id,
                cycles,
                expected_cycles,
                utilization,
                vcd_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                test_case_id,
                worker_id,
                status,
                failure_signature_id,
                cycles,
                expected_cycles,
                utilization,
                artifact_path,
            ),
        )


def test_comparison_rows_compute_status_and_perf_relationships():
    conn, baseline_id, current_id, _ = make_fixture_db()

    rows = fetch_comparison_rows(conn, baseline_id, current_id)
    by_name = {row["test_name"]: row for row in rows}

    assert by_name["new_fail"]["status_change_type"] == "new_failure"
    assert by_name["new_fail"]["perf_change_type"] == "perf_regression"
    assert by_name["new_fail"]["cycle_change_pct"] == 30.0
    assert by_name["fixed"]["status_change_type"] == "fixed"
    assert by_name["still_fail"]["status_change_type"] == "still_failing"
    assert by_name["slow"]["perf_change_type"] == "perf_regression"
    assert by_name["fast"]["perf_change_type"] == "perf_improvement"
    assert by_name["infra"]["is_infra_failure"] == 1


def test_comparison_summary_matches_python_analysis_categories():
    conn, baseline_id, current_id, _ = make_fixture_db()

    summary = summarize_comparison(conn, baseline_id, current_id)

    assert summary == {
        "compared_tests": 6,
        "new_failures": 2,
        "fixed_tests": 1,
        "still_failing": 1,
        "perf_regressions": 2,
        "perf_improvements": 1,
        "infra_failures": 1,
    }


def test_top_failure_signatures_groups_current_failures():
    conn, baseline_id, current_id, _ = make_fixture_db()

    signatures = top_failure_signatures(conn, baseline_id, current_id)

    assert signatures == [
        {"failure_signature": "ASSERTION_FAILED:packet_ordering", "result_count": 1},
        {"failure_signature": "ASSERTION_FAILED:valid_ready_protocol", "result_count": 1},
        {"failure_signature": "INFRA_FAILURE:sim_timeout", "result_count": 1},
    ]


def test_new_failures_returns_comparison_rows():
    conn, baseline_id, current_id, _ = make_fixture_db()

    rows = new_failures(conn, baseline_id, current_id)

    assert [row["test_name"] for row in rows] == ["new_fail", "infra"]


def test_worst_perf_regressions_orders_by_cycle_change():
    conn, baseline_id, current_id, _ = make_fixture_db()

    rows = worst_perf_regressions(conn, baseline_id, current_id)

    assert [row["test_name"] for row in rows] == ["slow", "new_fail"]
    assert rows[0]["cycle_change_pct"] == 30.0


def test_current_failures_by_worker_can_filter_to_dma():
    conn, _, current_id, _ = make_fixture_db()

    rows = current_failures_by_worker(conn, current_id, suite="dma")

    assert rows == [
        {
            "worker_name": "worker-2",
            "total_tests": 1,
            "failed_tests": 1,
            "failure_rate_pct": 100.0,
            "infra_failures": 0,
            "assertion_failures": 1,
        },
        {
            "worker_name": "worker-1",
            "total_tests": 2,
            "failed_tests": 1,
            "failure_rate_pct": 50.0,
            "infra_failures": 0,
            "assertion_failures": 1,
        },
    ]


def test_failed_test_vcds_returns_current_failure_artifacts():
    conn, _, current_id, _ = make_fixture_db()

    rows = failed_test_vcds(conn, current_id)

    assert [row["vcd_path"] for row in rows] == [
        "waves/new.vcd",
        "waves/still.vcd",
        "waves/infra.vcd",
    ]


def test_current_failures_returns_normalized_debug_fields():
    conn, _, current_id, _ = make_fixture_db()

    rows = current_failures(conn, current_id)

    assert rows[0]["failure_type"] == "ASSERTION_FAILED"
    assert rows[0]["test_family"] == "new"


def test_query_comparison_combines_question_and_filters():
    conn, baseline_id, current_id, _ = make_fixture_db()

    rows = query_comparison(
        conn,
        baseline_id,
        current_id,
        query_kind="current_failures",
        suite="dma",
        worker="worker-2",
        failure_type="ASSERTION_FAILED",
    )

    assert len(rows) == 1
    assert rows[0]["test_name"] == "still_fail"


def test_query_comparison_supports_slowdown_threshold():
    conn, baseline_id, current_id, _ = make_fixture_db()

    rows = query_comparison(
        conn,
        baseline_id,
        current_id,
        query_kind="all",
        min_cycle_change_pct=25.0,
    )

    assert [row["test_name"] for row in rows] == ["slow", "new_fail"]


def test_slowed_down_query_includes_passing_tests():
    conn, baseline_id, current_id, _ = make_fixture_db()

    rows = query_comparison(
        conn,
        baseline_id,
        current_id,
        query_kind="slowed_down",
    )

    assert [row["test_name"] for row in rows] == ["slow", "new_fail"]
    assert rows[0]["current_status"] == "PASS"


def test_query_comparison_rejects_unknown_query_kind():
    conn, baseline_id, current_id, _ = make_fixture_db()

    try:
        query_comparison(conn, baseline_id, current_id, query_kind="raw_sql_plz")
        assert False, "unknown query kind should fail"
    except ValueError:
        pass


def test_compare_run_to_many_summarizes_all_other_runs():
    conn, baseline_id, current_id, third_id = make_fixture_db()

    rows = compare_run_to_many(conn, baseline_id)

    assert rows == [
        {
            "compared_run_id": current_id,
            "compared_run": "run_002",
            "commit_hash": "def456",
            "created_at": "2026-06-21T00:01:00",
            "compared_tests": 6,
            "new_failures": 2,
            "fixed_tests": 1,
            "still_failing": 1,
            "slower_tests": 2,
            "infra_failures": 1,
        },
        {
            "compared_run_id": third_id,
            "compared_run": "run_003",
            "commit_hash": "ghi789",
            "created_at": "2026-06-21T00:02:00",
            "compared_tests": 6,
            "new_failures": 0,
            "fixed_tests": 1,
            "still_failing": 1,
            "slower_tests": 2,
            "infra_failures": 0,
        },
    ]


def test_compare_run_to_many_can_limit_compared_runs():
    conn, baseline_id, _, third_id = make_fixture_db()

    rows = compare_run_to_many(conn, baseline_id, compared_run_ids=[third_id])

    assert len(rows) == 1
    assert rows[0]["compared_run"] == "run_003"


def test_filter_values_lists_queryable_fields():
    conn, _, current_id, _ = make_fixture_db()

    values = filter_values(conn, current_id)

    assert values["suites"] == ["cache", "dma", "noc"]
    assert values["workers"] == ["worker-1", "worker-2", "worker-3", "worker-4"]
    assert values["failure_types"] == ["ASSERTION_FAILED", "INFRA_FAILURE"]
    assert values["assertions"] == [
        "packet_ordering",
        "sim_timeout",
        "valid_ready_protocol",
    ]


def test_schema_rejects_duplicate_result_identity_per_run():
    conn, baseline_id, _, _ = make_fixture_db()

    duplicate = (
        baseline_id,
        1,
        "worker-9",
        "PASS",
        None,
        100,
        100,
        0.8,
    )

    try:
        conn.execute(
            """
            INSERT INTO test_results (
                run_id,
                test_case_id,
                worker_name,
                status,
                failure_signature_id,
                cycles,
                expected_cycles,
                utilization
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            duplicate,
        )
        assert False, "duplicate result identity should fail"
    except sqlite3.IntegrityError:
        pass
