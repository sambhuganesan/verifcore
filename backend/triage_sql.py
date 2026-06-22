import sqlite3


COMPARISON_CTE = """
WITH regression_comparison AS (
    SELECT
        b.suite AS suite,
        b.test_name AS test_name,
        b.seed AS seed,

        b.status AS baseline_status,
        c.status AS current_status,

        b.cycles AS baseline_cycles,
        c.cycles AS current_cycles,
        c.cycles - b.cycles AS cycle_delta,
        ROUND(((c.cycles - b.cycles) * 100.0) / NULLIF(b.cycles, 0), 1)
            AS cycle_change_pct,

        b.worker_id AS baseline_worker_id,
        c.worker_id AS current_worker_id,

        c.failure_type AS failure_type,
        c.assertion_name AS assertion_name,
        c.artifact_path AS artifact_path,
        COALESCE(c.failure_type, 'none') || ':' || COALESCE(c.assertion_name, 'none')
            AS failure_signature,

        CASE
            WHEN b.status = 'PASS' AND c.status = 'FAIL' THEN 'new_failure'
            WHEN b.status = 'FAIL' AND c.status = 'PASS' THEN 'fixed'
            WHEN b.status = 'FAIL' AND c.status = 'FAIL' THEN 'still_failing'
            ELSE 'unchanged'
        END AS status_change_type,

        CASE
            WHEN c.cycles >= b.cycles * 1.2 THEN 'perf_regression'
            WHEN c.cycles < b.cycles THEN 'perf_improvement'
            ELSE 'perf_unchanged'
        END AS perf_change_type,

        CASE
            WHEN c.status = 'FAIL' AND c.failure_type = 'INFRA_FAILURE' THEN 1
            ELSE 0
        END AS is_infra_failure
    FROM result_details b
    JOIN result_details c
      ON b.suite = c.suite
     AND b.test_name = c.test_name
     AND b.seed = c.seed
    WHERE b.run_id = ?
      AND c.run_id = ?
)
"""


COMPARISON_COLUMNS = """
suite,
test_name,
seed,
baseline_status,
current_status,
baseline_cycles,
current_cycles,
cycle_delta,
cycle_change_pct,
baseline_worker_id,
current_worker_id,
failure_type,
assertion_name,
artifact_path,
failure_signature,
status_change_type,
perf_change_type,
is_infra_failure
"""


def fetch_comparison_rows(conn, baseline_run_id, current_run_id):
    conn.row_factory = _row_factory(conn.row_factory)
    cur = conn.cursor()
    cur.execute(
        COMPARISON_CTE
        + f"""
        SELECT {COMPARISON_COLUMNS}
        FROM regression_comparison
        ORDER BY suite, test_name, seed
        """,
        (baseline_run_id, current_run_id),
    )
    return [dict(row) for row in cur.fetchall()]


def summarize_comparison(conn, baseline_run_id, current_run_id):
    conn.row_factory = _row_factory(conn.row_factory)
    cur = conn.cursor()
    cur.execute(
        COMPARISON_CTE
        + """
        SELECT
            COUNT(*) AS compared_tests,
            SUM(status_change_type = 'new_failure') AS new_failures,
            SUM(status_change_type = 'fixed') AS fixed_tests,
            SUM(status_change_type = 'still_failing') AS still_failing,
            SUM(perf_change_type = 'perf_regression') AS perf_regressions,
            SUM(perf_change_type = 'perf_improvement') AS perf_improvements,
            SUM(is_infra_failure) AS infra_failures
        FROM regression_comparison
        """,
        (baseline_run_id, current_run_id),
    )
    return dict(cur.fetchone())


def top_failure_signatures(conn, baseline_run_id, current_run_id, limit=10):
    conn.row_factory = _row_factory(conn.row_factory)
    cur = conn.cursor()
    cur.execute(
        COMPARISON_CTE
        + """
        SELECT
            failure_signature,
            COUNT(*) AS result_count
        FROM regression_comparison
        WHERE current_status = 'FAIL'
        GROUP BY failure_signature
        ORDER BY result_count DESC, failure_signature ASC
        LIMIT ?
        """,
        (baseline_run_id, current_run_id, limit),
    )
    return [dict(row) for row in cur.fetchall()]


def _row_factory(existing_factory):
    return existing_factory or sqlite3.Row
