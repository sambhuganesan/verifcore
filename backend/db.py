import sqlite3


def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn):
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_name TEXT NOT NULL UNIQUE,
            commit_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS test_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            suite TEXT NOT NULL,
            test_name TEXT NOT NULL,
            seed INTEGER NOT NULL,
            test_family TEXT NOT NULL,
            UNIQUE(suite, test_name, seed)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS failure_signatures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            failure_type TEXT NOT NULL,
            assertion_name TEXT NOT NULL,
            UNIQUE(failure_type, assertion_name)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS test_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            test_case_id INTEGER NOT NULL,
            worker_name TEXT NOT NULL,
            status TEXT NOT NULL,
            failure_signature_id INTEGER,
            cycles INTEGER NOT NULL,
            expected_cycles INTEGER NOT NULL,
            utilization REAL NOT NULL,
            vcd_path TEXT,
            FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE,
            FOREIGN KEY(test_case_id) REFERENCES test_cases(id),
            FOREIGN KEY(failure_signature_id) REFERENCES failure_signatures(id),
            UNIQUE(run_id, test_case_id),
            CHECK(status IN ('PASS', 'FAIL')),
            CHECK(cycles >= 0),
            CHECK(expected_cycles >= 0),
            CHECK(utilization >= 0.0),
            CHECK(
                (status = 'PASS' AND failure_signature_id IS NULL)
                OR
                (status = 'FAIL' AND failure_signature_id IS NOT NULL)
            )
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_test_results_run
        ON test_results(run_id)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_test_results_test_case
        ON test_results(test_case_id)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_test_results_worker_name
        ON test_results(worker_name)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_test_results_failure_signature
        ON test_results(failure_signature_id)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_test_cases_suite
        ON test_cases(suite)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_test_cases_family
        ON test_cases(test_family)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_failure_signatures_type_assertion
        ON failure_signatures(failure_type, assertion_name)
    """)

    cur.execute("""
        CREATE VIEW IF NOT EXISTS result_details AS
        SELECT
            tr.id AS id,
            tr.run_id AS run_id,
            tc.suite AS suite,
            tc.test_name AS test_name,
            tc.seed AS seed,
            tc.test_family AS test_family,
            tr.worker_name AS worker_id,
            tr.worker_name AS worker_name,
            tr.status AS status,
            COALESCE(fs.failure_type, 'none') AS failure_type,
            COALESCE(fs.assertion_name, 'none') AS assertion_name,
            tr.vcd_path AS artifact_path,
            tr.vcd_path AS vcd_path,
            tr.cycles AS cycles,
            tr.expected_cycles AS expected_cycles,
            tr.utilization AS utilization
        FROM test_results tr
        JOIN test_cases tc
          ON tc.id = tr.test_case_id
        LEFT JOIN failure_signatures fs
          ON fs.id = tr.failure_signature_id
    """)

    conn.commit()
