import argparse
import json
import re
from datetime import datetime

from backend import db


def test_family(test_name):
    return re.sub(r"_\d+$", "", test_name)


def get_or_create_test_case(cur, record):
    cur.execute(
        """
        INSERT OR IGNORE INTO test_cases (suite, test_name, seed, test_family)
        VALUES (?, ?, ?, ?)
        """,
        (
            record["suite"],
            record["test_name"],
            record["seed"],
            test_family(record["test_name"]),
        ),
    )
    cur.execute(
        """
        SELECT id
        FROM test_cases
        WHERE suite = ?
          AND test_name = ?
          AND seed = ?
        """,
        (record["suite"], record["test_name"], record["seed"]),
    )
    return cur.fetchone()[0]


def get_or_create_failure_signature(cur, record):
    if record["status"] != "FAIL":
        return None

    failure_type = record.get("failure_type")
    assertion_name = record.get("assertion_name")

    if not failure_type or failure_type == "none":
        failure_type = "UNKNOWN_FAILURE"

    if not assertion_name or assertion_name == "none":
        assertion_name = "unknown"

    cur.execute(
        """
        INSERT OR IGNORE INTO failure_signatures (failure_type, assertion_name)
        VALUES (?, ?)
        """,
        (failure_type, assertion_name),
    )
    cur.execute(
        """
        SELECT id
        FROM failure_signatures
        WHERE failure_type = ?
          AND assertion_name = ?
        """,
        (failure_type, assertion_name),
    )
    return cur.fetchone()[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("jsonl_path")

    args = parser.parse_args()
    conn = db.connect(args.db)
    db.init_db(conn)
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO runs (run_name, commit_hash, created_at)
        VALUES (?, ?, ?)
        """,
        (args.run_name, args.commit, datetime.now().isoformat()),
    )
    run_id = cur.lastrowid

    inserted = 0
    with open(args.jsonl_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            test_case_id = get_or_create_test_case(cur, record)
            failure_signature_id = get_or_create_failure_signature(cur, record)
            cur.execute(
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
                    record["worker_id"],
                    record["status"],
                    failure_signature_id,
                    record["cycles"],
                    record["expected_cycles"],
                    record["utilization"],
                    record["artifact_path"],
                ),
            )

            inserted += 1

    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
