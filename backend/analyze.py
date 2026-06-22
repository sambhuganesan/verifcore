import argparse
from backend import db

def get_run_id(conn, run_name):
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id
        FROM runs
        WHERE run_name = ?
        """,
        (run_name,),
    )

    row = cur.fetchone()

    if row is None:
        raise ValueError(f"Unknown run: {run_name}")

    return row[0]


def count_results(conn, run_id):
    cur = conn.cursor()

    cur.execute(
        """
        SELECT COUNT(*)
        FROM test_results
        WHERE run_id = ?
        """,
        (run_id,),
    )

    return cur.fetchone()[0]


def load_results(conn, run_id):
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
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
        FROM result_details
        WHERE run_id = ?
        """,
        (run_id,),
    )

    results = {}

    for row in cur.fetchall():
        record = {
            "suite": row[0],
            "test_name": row[1],
            "seed": row[2],
            "worker_id": row[3],
            "status": row[4],
            "failure_type": row[5],
            "assertion_name": row[6],
            "artifact_path": row[7],
            "cycles": row[8],
            "expected_cycles": row[9],
            "utilization": row[10],
        }

        key = (record["suite"], record["test_name"], record["seed"])
        results[key] = record

    return results


def is_perf_regression(baseline_cycles, current_cycles, threshold=0.2):
    return current_cycles >= baseline_cycles * (1 + threshold)


def is_perf_improvement(baseline_cycles, current_cycles, threshold=0.0):
    return current_cycles < baseline_cycles * (1 - threshold)


def compare_runs(baseline_results, current_results):
    new_failures = []
    fixed_tests = []
    still_failing = []
    perf_regressions = []
    perf_improvements = []
    infra_failures = []

    common_keys = sorted(baseline_results.keys() & current_results.keys())

    for key in common_keys:
        baseline = baseline_results[key]
        current = current_results[key]

        if baseline["status"] == "PASS" and current["status"] == "FAIL":
            new_failures.append(current)

        if baseline["status"] == "FAIL" and current["status"] == "PASS":
            fixed_tests.append(current)

        if baseline["status"] == "FAIL" and current["status"] == "FAIL":
            still_failing.append(current)

        if is_perf_regression(baseline["cycles"], current["cycles"]):
            perf_regressions.append((baseline, current))

        if is_perf_improvement(baseline["cycles"], current["cycles"]):
            perf_improvements.append((baseline, current))

        if current["status"] == "FAIL" and current["failure_type"] == "INFRA_FAILURE":
            infra_failures.append(current)

    return {
        "new_failures": new_failures,
        "fixed_tests": fixed_tests,
        "still_failing": still_failing,
        "perf_regressions": perf_regressions,
        "perf_improvements": perf_improvements,
        "infra_failures": infra_failures,
    }


def group_failure_signatures(results):
    groups = {}

    for record in results.values():
        if record["status"] != "FAIL":
            continue

        signature = f'{record["failure_type"]}:{record["assertion_name"]}'

        if signature not in groups:
            groups[signature] = 0

        groups[signature] += 1

    return sorted(groups.items(), key=lambda item: item[1], reverse=True)


def get_flaky_tests(conn):
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            suite,
            test_name,
            seed,
            GROUP_CONCAT(DISTINCT status) AS statuses,
            COUNT(*) AS observations
        FROM result_details
        GROUP BY suite, test_name, seed
        HAVING COUNT(DISTINCT status) > 1
        ORDER BY suite, test_name, seed
        """
    )

    flaky = []

    for row in cur.fetchall():
        flaky.append(
            {
                "suite": row[0],
                "test_name": row[1],
                "seed": row[2],
                "statuses": row[3],
                "observations": row[4],
            }
        )

    return flaky


def format_test(record):
    base = (
        f'{record["suite"]}.{record["test_name"]} '
        f'seed={record["seed"]} '
        f'status={record["status"]} '
        f'cycles={record["cycles"]}'
    )

    if record["status"] == "FAIL":
        base += f' failure={record["failure_type"]}:{record["assertion_name"]}'

    return base


def print_test_examples(title, records, limit=5):
    print()
    print(title)
    print("-" * len(title))

    if not records:
        print("none")
        return

    for record in records[:limit]:
        print(format_test(record))

    if len(records) > limit:
        print(f"... and {len(records) - limit} more")


def print_perf_examples(title, perf_results, limit=5):
    print()
    print(title)
    print("-" * len(title))

    if not perf_results:
        print("none")
        return

    for baseline, current in perf_results[:limit]:
        delta = current["cycles"] - baseline["cycles"]
        pct = (delta / baseline["cycles"]) * 100
        sign = "+" if pct >= 0 else ""

        print(
            f'{current["suite"]}.{current["test_name"]} '
            f'seed={current["seed"]} '
            f'{baseline["cycles"]} -> {current["cycles"]} '
            f'({sign}{pct:.1f}%)'
        )

    if len(perf_results) > limit:
        print(f"... and {len(perf_results) - limit} more")


def print_signature_groups(signature_groups, limit=10):
    print()
    print("Failure signature groups")
    print("------------------------")

    if not signature_groups:
        print("none")
        return

    for signature, count in signature_groups[:limit]:
        print(f"{signature}: {count}")

    if len(signature_groups) > limit:
        print(f"... and {len(signature_groups) - limit} more")


def print_flaky_tests(flaky_tests, limit=10):
    print()
    print("status_changing examples")
    print("------------------------")

    if not flaky_tests:
        print("none")
        return

    for test in flaky_tests[:limit]:
        print(
            f'{test["suite"]}.{test["test_name"]} '
            f'seed={test["seed"]} '
            f'statuses={test["statuses"]} '
            f'observations={test["observations"]}'
        )

    if len(flaky_tests) > limit:
        print(f"... and {len(flaky_tests) - limit} more")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--current", required=True)

    args = parser.parse_args()

    conn = db.connect(args.db)

    baseline_id = get_run_id(conn, args.baseline)
    current_id = get_run_id(conn, args.current)

    baseline_count = count_results(conn, baseline_id)
    current_count = count_results(conn, current_id)

    baseline_results = load_results(conn, baseline_id)
    current_results = load_results(conn, current_id)

    comparison = compare_runs(baseline_results, current_results)
    signature_groups = group_failure_signatures(current_results)
    flaky_tests = get_flaky_tests(conn)

    print("VerifCore Regression Report")
    print("===========================")
    print(f"Baseline {args.baseline}: {baseline_count} tests")
    print(f"Current  {args.current}: {current_count} tests")

    print()
    print("Summary")
    print("-------")
    print(f'New failures: {len(comparison["new_failures"])}')
    print(f'Corrected tests: {len(comparison["fixed_tests"])}')
    print(f'Still failing: {len(comparison["still_failing"])}')
    print(f'Regressed: {len(comparison["perf_regressions"])}')
    print(f'Improved: {len(comparison["perf_improvements"])}')
    print(f'Infra failures: {len(comparison["infra_failures"])}')
    print(f"status_changing: {len(flaky_tests)}")

    print_test_examples("New failure examples", comparison["new_failures"])
    print_test_examples("Corrected test examples", comparison["fixed_tests"])
    print_test_examples("Still failing examples", comparison["still_failing"])
    print_perf_examples("Regressed examples", comparison["perf_regressions"])
    print_perf_examples("Improved examples", comparison["perf_improvements"])
    print_test_examples("Infra failure examples", comparison["infra_failures"])
    print_signature_groups(signature_groups)
    print_flaky_tests(flaky_tests)

    conn.close()


if __name__ == "__main__":
    main()
