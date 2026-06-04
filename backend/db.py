import sqlite3 

def connect(db_path):
    return sqlite3.connect(db_path)

def init_db(conn):
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
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            suite TEXT NOT NULL,
            test_name TEXT NOT NULL,
            seed INTEGER NOT NULL,
            worker_id TEXT NOT NULL,
            status TEXT NOT NULL,
            failure_type TEXT,
            assertion_name TEXT,
            artifact_path TEXT,
            cycles INTEGER NOT NULL,
            expected_cycles INTEGER NOT NULL,
            utilization REAL NOT NULL,
            FOREIGN KEY(run_id) REFERENCES runs(id)
        )
    """)

    conn.commit()
