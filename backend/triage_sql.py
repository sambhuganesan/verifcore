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


QUERY_KINDS = {
    "all": "All compared tests",
    "new_failures": "New failures",
    "current_failures": "Current failures",
    "fixed": "Fixed tests",
    "still_failing": "Still failing",
    "slowed_down": "Slowed down",
    "vcds": "Failures with VCDs",
}


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


def query_comparison(
    conn,
    baseline_run_id,
    current_run_id,
    query_kind="all",
    suite=None,
    worker=None,
    failure_type=None,
    assertion=None,
    min_cycle_change_pct=None,
    limit=200,
):
    if query_kind not in QUERY_KINDS:
        raise ValueError(f"Unsupported query kind: {query_kind}")

    conn.row_factory = _row_factory(conn.row_factory)
    where_clauses = []
    params = [baseline_run_id, current_run_id]

    if query_kind == "new_failures":
        where_clauses.append("status_change_type = 'new_failure'")
    elif query_kind == "current_failures":
        where_clauses.append("current_status = 'FAIL'")
    elif query_kind == "fixed":
        where_clauses.append("status_change_type = 'fixed'")
    elif query_kind == "still_failing":
        where_clauses.append("status_change_type = 'still_failing'")
    elif query_kind == "slowed_down":
        where_clauses.append("perf_change_type = 'perf_regression'")
    elif query_kind == "vcds":
        where_clauses.append("current_status = 'FAIL'")
        where_clauses.append("artifact_path IS NOT NULL")

    if suite:
        where_clauses.append("suite = ?")
        params.append(suite)

    if worker:
        where_clauses.append("current_worker_id = ?")
        params.append(worker)

    if failure_type:
        where_clauses.append("failure_type = ?")
        params.append(failure_type)

    if assertion:
        where_clauses.append("assertion_name = ?")
        params.append(assertion)

    if min_cycle_change_pct is not None:
        where_clauses.append("cycle_change_pct >= ?")
        params.append(min_cycle_change_pct)

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    order_sql = "ORDER BY suite, test_name, seed"
    if query_kind == "slowed_down" or min_cycle_change_pct is not None:
        order_sql = "ORDER BY cycle_change_pct DESC, suite, test_name, seed"

    params.append(limit)

    cur = conn.cursor()
    cur.execute(
        COMPARISON_CTE
        + f"""
        SELECT {COMPARISON_COLUMNS}
        FROM regression_comparison
        {where_sql}
        {order_sql}
        LIMIT ?
        """,
        params,
    )
    return [dict(row) for row in cur.fetchall()]


def filter_values(conn, current_run_id):
    conn.row_factory = _row_factory(conn.row_factory)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT suite
        FROM result_details
        WHERE run_id = ?
        ORDER BY suite
        """,
        (current_run_id,),
    )
    suites = [row["suite"] for row in cur.fetchall()]

    cur.execute(
        """
        SELECT DISTINCT worker_name
        FROM result_details
        WHERE run_id = ?
        ORDER BY worker_name
        """,
        (current_run_id,),
    )
    workers = [row["worker_name"] for row in cur.fetchall()]

    cur.execute(
        """
        SELECT DISTINCT failure_type
        FROM result_details
        WHERE run_id = ?
          AND failure_type != 'none'
        ORDER BY failure_type
        """,
        (current_run_id,),
    )
    failure_types = [row["failure_type"] for row in cur.fetchall()]

    cur.execute(
        """
        SELECT DISTINCT assertion_name
        FROM result_details
        WHERE run_id = ?
          AND assertion_name != 'none'
        ORDER BY assertion_name
        """,
        (current_run_id,),
    )
    assertions = [row["assertion_name"] for row in cur.fetchall()]

    return {
        "suites": suites,
        "workers": workers,
        "failure_types": failure_types,
        "assertions": assertions,
    }


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


def new_failures(conn, baseline_run_id, current_run_id, limit=100):
    conn.row_factory = _row_factory(conn.row_factory)
    cur = conn.cursor()
    cur.execute(
        COMPARISON_CTE
        + f"""
        SELECT {COMPARISON_COLUMNS}
        FROM regression_comparison
        WHERE status_change_type = 'new_failure'
        ORDER BY suite, test_name, seed
        LIMIT ?
        """,
        (baseline_run_id, current_run_id, limit),
    )
    return [dict(row) for row in cur.fetchall()]


def worst_perf_regressions(conn, baseline_run_id, current_run_id, limit=25):
    conn.row_factory = _row_factory(conn.row_factory)
    cur = conn.cursor()
    cur.execute(
        COMPARISON_CTE
        + f"""
        SELECT {COMPARISON_COLUMNS}
        FROM regression_comparison
        WHERE perf_change_type = 'perf_regression'
        ORDER BY cycle_change_pct DESC, suite, test_name, seed
        LIMIT ?
        """,
        (baseline_run_id, current_run_id, limit),
    )
    return [dict(row) for row in cur.fetchall()]


def current_failures_by_worker(conn, current_run_id, suite=None):
    conn.row_factory = _row_factory(conn.row_factory)
    params = [current_run_id]
    suite_filter = ""
    if suite:
        suite_filter = "AND suite = ?"
        params.append(suite)

    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT
            worker_name,
            COUNT(*) AS total_tests,
            SUM(status = 'FAIL') AS failed_tests,
            ROUND(SUM(status = 'FAIL') * 100.0 / COUNT(*), 1)
                AS failure_rate_pct,
            SUM(failure_type = 'INFRA_FAILURE') AS infra_failures,
            SUM(failure_type = 'ASSERTION_FAILED') AS assertion_failures
        FROM result_details
        WHERE run_id = ?
          {suite_filter}
        GROUP BY worker_name
        ORDER BY failed_tests DESC, failure_rate_pct DESC, worker_name ASC
        """,
        params,
    )
    return [dict(row) for row in cur.fetchall()]


def failed_test_vcds(conn, current_run_id, limit=200):
    conn.row_factory = _row_factory(conn.row_factory)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            suite,
            test_name,
            seed,
            worker_name,
            failure_type,
            assertion_name,
            vcd_path
        FROM result_details
        WHERE run_id = ?
          AND status = 'FAIL'
          AND vcd_path IS NOT NULL
        ORDER BY suite, test_name, seed
        LIMIT ?
        """,
        (current_run_id, limit),
    )
    return [dict(row) for row in cur.fetchall()]


def current_failures(conn, current_run_id, limit=200):
    conn.row_factory = _row_factory(conn.row_factory)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            suite,
            test_name,
            seed,
            test_family,
            worker_name,
            failure_type,
            assertion_name,
            vcd_path,
            cycles,
            expected_cycles
        FROM result_details
        WHERE run_id = ?
          AND status = 'FAIL'
        ORDER BY suite, test_name, seed
        LIMIT ?
        """,
        (current_run_id, limit),
    )
    return [dict(row) for row in cur.fetchall()]


def _row_factory(existing_factory):
    return existing_factory or sqlite3.Row
