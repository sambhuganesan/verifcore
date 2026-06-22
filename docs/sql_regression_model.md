# VerifCore SQL Regression Model

VerifCore models regression triage with four core tables:

```text
runs
test_cases
failure_signatures
test_results
```

`test_results` is the central fact table. Each row connects one run, one stable
test case, one worker name, and optionally one failure signature.

```text
runs 1 ─── * test_results * ─── 1 test_cases
                  |
                  * ─── 0/1 failure_signatures
```

Worker name and VCD path are stored directly on `test_results` in Phase 1.
They are queryable fields, but they are not separate entities yet.

## Tables

### `runs`

```sql
CREATE TABLE runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_name TEXT NOT NULL UNIQUE,
    commit_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

### `test_cases`

```sql
CREATE TABLE test_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    suite TEXT NOT NULL,
    test_name TEXT NOT NULL,
    seed INTEGER NOT NULL,
    test_family TEXT NOT NULL,
    UNIQUE(suite, test_name, seed)
);
```

The stable identity is:

```text
suite + test_name + seed
```

This lets VerifCore compare the same logical test across multiple runs.

### `failure_signatures`

```sql
CREATE TABLE failure_signatures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    failure_type TEXT NOT NULL,
    assertion_name TEXT NOT NULL,
    UNIQUE(failure_type, assertion_name)
);
```

Examples:

```text
ASSERTION_FAILED / valid_ready_protocol
ASSERTION_FAILED / packet_ordering
INFRA_FAILURE    / sim_timeout
```

Passing tests have `failure_signature_id = NULL`.

### `test_results`

```sql
CREATE TABLE test_results (
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
);
```

## Flattened Analysis View

The normalized schema is good for integrity. Analysis code often wants a
convenient row shape, so VerifCore exposes `result_details`:

```text
result_details =
test_results
JOIN test_cases
LEFT JOIN failure_signatures
```

It provides columns such as:

```text
run_id
suite
test_name
seed
test_family
worker_name
status
failure_type
assertion_name
vcd_path
cycles
expected_cycles
utilization
```

## Comparison Query Pattern

Baseline/current comparison is a self-join through `test_case_id`:

```sql
SELECT
    tc.suite,
    tc.test_name,
    tc.seed,
    b.status AS baseline_status,
    c.status AS current_status,
    b.cycles AS baseline_cycles,
    c.cycles AS current_cycles,
    ROUND(((c.cycles - b.cycles) * 100.0) / NULLIF(b.cycles, 0), 1)
        AS cycle_change_pct,
    fs.failure_type,
    fs.assertion_name,
    c.worker_name,
    c.vcd_path
FROM test_results b
JOIN test_results c
  ON b.test_case_id = c.test_case_id
JOIN test_cases tc
  ON tc.id = c.test_case_id
LEFT JOIN failure_signatures fs
  ON fs.id = c.failure_signature_id
WHERE b.run_id = ?
  AND c.run_id = ?;
```

## Questions This Supports

New failures:

```sql
WHERE b.status = 'PASS'
  AND c.status = 'FAIL'
```

Fixed tests:

```sql
WHERE b.status = 'FAIL'
  AND c.status = 'PASS'
```

Still failing:

```sql
WHERE b.status = 'FAIL'
  AND c.status = 'FAIL'
```

Top current failure signatures:

```sql
SELECT fs.failure_type, fs.assertion_name, COUNT(*) AS result_count
FROM test_results tr
JOIN failure_signatures fs
  ON fs.id = tr.failure_signature_id
WHERE tr.run_id = ?
  AND tr.status = 'FAIL'
GROUP BY fs.failure_type, fs.assertion_name
ORDER BY result_count DESC;
```

DMA failures by worker:

```sql
SELECT tr.worker_name, COUNT(*) AS dma_failures
FROM test_results tr
JOIN test_cases tc
  ON tc.id = tr.test_case_id
WHERE tr.run_id = ?
  AND tc.suite = 'dma'
  AND tr.status = 'FAIL'
GROUP BY tr.worker_name
ORDER BY dma_failures DESC;
```

VCD files for current failures:

```sql
SELECT tc.suite, tc.test_name, tc.seed, tr.vcd_path
FROM test_results tr
JOIN test_cases tc
  ON tc.id = tr.test_case_id
WHERE tr.run_id = ?
  AND tr.status = 'FAIL'
  AND tr.vcd_path IS NOT NULL;
```

Tests that slowed down the most:

```sql
SELECT
    tc.suite,
    tc.test_name,
    tc.seed,
    b.cycles AS baseline_cycles,
    c.cycles AS current_cycles,
    ROUND(((c.cycles - b.cycles) * 100.0) / NULLIF(b.cycles, 0), 1)
        AS cycle_change_pct
FROM test_results b
JOIN test_results c
  ON b.test_case_id = c.test_case_id
JOIN test_cases tc
  ON tc.id = c.test_case_id
WHERE b.run_id = ?
  AND c.run_id = ?
  AND c.cycles >= b.cycles * 1.2
ORDER BY cycle_change_pct DESC;
```

Historical assertion failures:

```sql
SELECT r.run_name, tc.suite, tc.test_name, tc.seed
FROM test_results tr
JOIN runs r
  ON r.id = tr.run_id
JOIN test_cases tc
  ON tc.id = tr.test_case_id
JOIN failure_signatures fs
  ON fs.id = tr.failure_signature_id
WHERE fs.assertion_name = ?
ORDER BY r.created_at;
```
