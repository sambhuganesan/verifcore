import argparse
import json
from datetime import datetime

from backend import db

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
            cur.execute(
                """
                INSERT INTO results (
                    run_id,
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
                    utilization
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    record["suite"],
                    record["test_name"],
                    record["seed"],
                    record["worker_id"],
                    record["status"],
                    record["failure_type"],
                    record["assertion_name"],
                    record["artifact_path"],
                    record["cycles"],
                    record["expected_cycles"],
                    record["utilization"],
                ),
            )

            inserted += 1

    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()