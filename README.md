# VerifCore

VerifCore is a small C++/Python/SQLite project inspired by design verification regression tooling.

The technical goal was to build the core pipeline directly instead of wrapping a large parsing or analytics framework. The C++ parser is a small systems-programming component built with the standard library: it reads log lines, classifies records, parses key/value fields, and emits JSONL without external C++ dependencies. The Python backend also stays lightweight and uses the standard library for log generation, SQLite ingestion, and run comparison. Streamlit is used only for the local demo UI.

## Quick Start

From the `verifcore/` directory:

```bash
make demo NUM_TESTS=1000
```

This builds the C++ parser, generates baseline/regression logs, parses them into JSONL, ingests them into SQLite, and prints the regression report.

To launch the local UI:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
make ui
```

Then open the Streamlit URL printed in the terminal.

---

It demonstrates the workflow of turning noisy regression logs into structured signals:

* new failures
* corrected tests
* still-failing tests
* infrastructure failures
* regressed tests
* improved tests
* failure signature groups
* `status_changing` tests

The project is intentionally small and it mirrors the shape of real regression infrastructure: logs are generated, parsed, normalized into JSONL, ingested into a database, and analyzed across runs.

---

## Why this exists

Hardware design verification teams run large regression suites to check whether a design still behaves correctly after code changes.

A single regression run can contain many individual tests. A test may 
* pass
* fail due to a design assertion 
* fail because of infrastructure issues
* become slower than before. 

Raw logs are hard to inspect manually, especially when there are hundreds or thousands of tests.

VerifCore shows how to convert those raw logs into a queryable dataset and then produce a useful regression report. It answers the question:

> What changed between the baseline run and the current run?

---

## High-level pipeline

```text
synthetic DV logs
    -> C++ streaming parser
    -> JSONL test records
    -> SQLite ingestion
    -> regression analyzer
    -> terminal report or Streamlit UI
```

The same SQLite database powers both the terminal report and the local Streamlit dashboard.

---

## Project structure

```text
verifcore/
├── README.md
├── Makefile
├── requirements.txt
├── log_parser
├── verifcore.db
├── .streamlit/
│   └── config.toml
│
├── cpp/
│   ├── main.cc
│   ├── line_reader.h
│   ├── line_reader.cc
│   ├── line_classifier.h
│   ├── line_classifier.cc
│   ├── kv_parser.h
│   ├── kv_parser.cc
│   ├── string_utils.h
│   ├── string_utils.cc
│   ├── record_parser.h
│   ├── record_parser.cc
│   ├── test_result.h
│   └── test_result.cc
│
├── backend/
│   ├── __init__.py
│   ├── generate_logs.py
│   ├── db.py
│   ├── ingest.py
│   └── analyze.py
│
├── ui/
│   └── app.py
│
├── sample_logs/
│   ├── manual.log
│   ├── run_001.log
│   └── run_002.log
│
├── parsed/
│   ├── run_001.jsonl
│   └── run_002.jsonl
│
└── tests/
    └── test_analysis.py
```

---

## Synthetic log format

VerifCore uses a small fake DV-style log format.

A whole log file represents one regression run. Each test result is represented by a block of lines.

A passing test looks like this:

```text
[RUN] suite=dma test=aligned_burst_0 seed=1000 worker=worker-0
[METRIC] cycles=684 expected_cycles=700 utilization=0.8
[PASS]
```

A failing test looks like this:

```text
[RUN] suite=systolic_array test=backpressure_13 seed=1013 worker=worker-5
[METRIC] cycles=1035 expected_cycles=1025 utilization=0.72
[FAIL] type=ASSERTION_FAILED assertion=fifo_no_overflow artifact=waves/systolic_array_backpressure_13_seed1013.vcd
```

Each test record contains:

| Field             | Meaning                                                         |
| ----------------- | --------------------------------------------------------------- |
| `suite`           | Logical test suite, such as `dma`, `cache`, or `systolic_array` |
| `test`            | Test name within the suite                                      |
| `seed`            | Deterministic random seed for the test                          |
| `worker`          | Fake worker that ran the test                                   |
| `cycles`          | Actual simulated hardware cycles taken                          |
| `expected_cycles` | Expected cycle count for the test                               |
| `utilization`     | Fake utilization metric                                         |
| `status`          | `PASS` or `FAIL`                                                |
| `type`            | Failure type, such as `ASSERTION_FAILED` or `INFRA_FAILURE`     |
| `assertion`       | Assertion or failure signature                                  |
| `artifact`        | Path to a fake waveform artifact                                |

The identity of a test is:

```text
suite + test_name + seed
```

Identity is stable across runs, so VerifCore can compare the same test in `run_001` and `run_002`.

---

## Design verification concepts used

VerifCore uses a few simplified hardware verification ideas.

A **clock cycle** is one simulated hardware clock tick. It is not wall-clock time.

A **signal** is a hardware value over time, such as a wire or register.

A **waveform file**, such as a `.vcd`, records signal values over simulated time. In this project, waveform paths are fake artifact paths used for realism.

A **valid/ready protocol** is a common hardware handshake. A transfer happens when `valid=1` and `ready=1`.

**Backpressure** happens when downstream logic is not ready to receive data, so it sets `ready=0`. Backpressure itself is not a bug. A bug happens if the upstream logic mishandles it, for example by changing data while `valid=1` and `ready=0`.

An **assertion failure** means the design violated a rule that the test expected to hold.

An **infrastructure failure** means the failure may not be caused by the design itself. Examples include simulator timeout, worker failure, environment issue, or missing artifact.

### Test suites

A **test suite** is a logical group of tests for one area of the design. VerifCore generates these synthetic suites:

| Suite            | Meaning                                                                 |
| ---------------- | ----------------------------------------------------------------------- |
| `dma`            | Direct Memory Access logic, which moves blocks of data without CPU help |
| `systolic_array` | Matrix/AI accelerator compute fabric, like the datapath used in ML chips |
| `cache`          | Cache behavior, such as storing, reusing, and invalidating data          |
| `noc`            | Network-on-chip routing between hardware blocks                          |
| `decoder`        | Packet or instruction decode logic                                       |

The generated test names describe the kind of scenario being exercised:

| Test family          | Meaning                                                             |
| -------------------- | ------------------------------------------------------------------- |
| `aligned_burst`      | Burst memory transfer with aligned addresses                         |
| `backpressure`       | Valid/ready flow control when downstream logic temporarily stalls     |
| `randomized_smoke`   | Broad randomized sanity test                                         |
| `reset_recovery`     | Behavior after reset is asserted and released                        |
| `protocol_stress`    | Heavy protocol-level traffic intended to expose edge cases            |

### Failure Types

VerifCore uses two synthetic failure types:

| Failure type       | Meaning                                                                 |
| ------------------ | ----------------------------------------------------------------------- |
| `ASSERTION_FAILED` | The design broke a rule the test was checking                           |
| `INFRA_FAILURE`    | The run failed for infrastructure reasons, such as a simulator timeout   |

The `assertion` field gives the more specific failure signature:

| Assertion                  | Meaning                                                                     |
| -------------------------- | --------------------------------------------------------------------------- |
| `valid_ready_protocol`     | A valid/ready handshake rule was violated                                    |
| `fifo_no_overflow`         | A FIFO queue was written when it was already full                            |
| `reset_clears_state`       | State that should be cleared by reset was still present afterward            |
| `packet_ordering`          | Packets came out in the wrong order                                          |
| `sim_timeout`              | The simulator timed out before the test completed; this is an infra failure  |

---

## Synthetic regression generation

The generator creates two fake regression logs.

Baseline run:

```bash
python3 -m backend.generate_logs \
  --out sample_logs/run_001.log \
  --seed 1 \
  --num-tests <count>
```

Current run with injected regressions:

```bash
python3 -m backend.generate_logs \
  --out sample_logs/run_002.log \
  --seed 2 \
  --num-tests <count> \
  --inject-regressions
```

The two runs share stable test identities:

```text
suite + test_name + seed
```

The current run intentionally injects useful regression-analysis cases:

* new failures
* corrected tests
* still-failing tests
* regressed tests
* improved tests
* infrastructure failures
* repeated failure signatures

This gives the analyzer meaningful data to compare.

---

## C++ parser

The C++ parser reads raw log files and writes one JSON object per test result.

Build:

```bash
make build
```

The Makefile compiles `log_parser` from `cpp/*.cc`.

Parse logs:

```bash
./log_parser sample_logs/run_001.log > parsed/run_001.jsonl
./log_parser sample_logs/run_002.log > parsed/run_002.jsonl
```

The parser is split into small components:

| Component         | Responsibility                                                                  |
| ----------------- | ------------------------------------------------------------------------------- |
| `line_reader`     | Reads raw bytes using POSIX `open/read/close`, handles arbitrary chunks, splits lines |
| `line_classifier` | Classifies lines as `RUN`, `METRIC`, `PASS`, `FAIL`, or `UNKNOWN`               |
| `kv_parser`       | Parses `key=value` fields                                                       |
| `record_parser`   | Builds complete `TestResult` records from classified lines                      |
| `test_result`     | Stores test fields and serializes results as JSON                               |

The parser classifies lines and maintains two boolean flags 
have_run and have_metric which indiciate if we are on the 
current test. This makes the design more robust and closer to real log-processing infrastructure.

---

## JSONL output

The parser writes JSONL: one JSON object per line.

Example:

```json
{"suite":"dma","test_name":"aligned_burst_0","seed":1000,"worker_id":"worker-0","cycles":684,"expected_cycles":700,"utilization":0.8,"status":"FAIL","failure_type":"ASSERTION_FAILED","assertion_name":"valid_ready_protocol","artifact_path":"waves/dma_aligned_burst_0_seed1000.vcd"}
```

JSONL is useful because large regression outputs can be streamed line by line instead of loaded as one giant JSON array.

---

## SQLite ingestion

The ingestion layer stores parsed results in SQLite.

Ingest baseline:

```bash
python3 -m backend.ingest \
  --db verifcore.db \
  --run-name run_001 \
  --commit abc123 \
  parsed/run_001.jsonl
```

Ingest current run:

```bash
python3 -m backend.ingest \
  --db verifcore.db \
  --run-name run_002 \
  --commit def456 \
  parsed/run_002.jsonl
```

SQLite stores the data in a single local file:

```text
verifcore.db
```

---

## Database schema

VerifCore uses two tables: `runs` and `results`.

### `runs`

One row per regression run.

```sql
CREATE TABLE runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_name TEXT NOT NULL UNIQUE,
    commit_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

Example:

| id | run_name | commit_hash | created_at |
| -: | -------- | ----------- | ---------- |
|  1 | run_001  | abc123      | timestamp  |
|  2 | run_002  | def456      | timestamp  |

### `results`

One row per test result.

```sql
CREATE TABLE results (
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
);
```

So for example, with two runs of 200 tests each, the database contains:

```text
runs:    2 rows
results: 400 rows
```

---

## Regression analyzer

Run:

```bash
python3 -m backend.analyze \
  --db verifcore.db \
  --baseline run_001 \
  --current run_002
```

The analyzer compares tests by:

```text
suite + test_name + seed
```

It then reports several categories.

### New failures

A test passed in the baseline run and failed in the current run.

```text
baseline: PASS
current:  FAIL
```

### Corrected tests

A test failed in the baseline run and passed in the current run.

```text
baseline: FAIL
current:  PASS
```

### Still failing

A test failed in both runs.

```text
baseline: FAIL
current:  FAIL
```

### Regressed

A test is regressed if current cycles are at least 20% higher than baseline cycles.

```text
current_cycles >= baseline_cycles * 1.20
```

Example:

```text
baseline cycles = 684
current cycles  = 863

684 * 1.20 = 820.8
863 >= 820.8
```

So this test is regressed.

### Improved

A test is improved if current cycles are lower than baseline cycles.

```text
current_cycles < baseline_cycles
```

This highlights successful changes where the current run got faster.

### Infrastructure failures

A current-run failure is counted as infrastructure-related if:

```text
status == FAIL
failure_type == INFRA_FAILURE
```

### Failure signature groups

Current failures are grouped by:

```text
failure_type + ":" + assertion_name
```

Example groups:

```text
INFRA_FAILURE:sim_timeout
ASSERTION_FAILED:fifo_no_overflow
ASSERTION_FAILED:valid_ready_protocol
```

This helps reduce many raw failures into a smaller number of debug buckets.

### `status_changing`

Across all stored runs, VerifCore finds tests that have appeared as both `PASS` and `FAIL`.

This is labeled `status_changing` because with only two different commits, a status change may be a real regression or fix rather than true flakiness. True flakiness usually requires repeated runs under the same commit/configuration.

---

## Example analyzer output

```text
VerifCore Regression Report
===========================
Baseline run_001: 200 tests
Current  run_002: 200 tests

Summary
-------
New failures: 19
Corrected tests: 7
Still failing: 9
Regressed: 10
Improved: 90
Infra failures: 9
status_changing: 26

Failure signature groups
------------------------
INFRA_FAILURE:sim_timeout: 9
ASSERTION_FAILED:fifo_no_overflow: 7
ASSERTION_FAILED:packet_ordering: 7
ASSERTION_FAILED:reset_clears_state: 3
ASSERTION_FAILED:valid_ready_protocol: 2
```

---

## Tests

Run:

```bash
python3 -m pytest tests
```

The current tests cover:

* performance regression detection
* failure signature grouping
* ignoring passing tests in signature groups
* run comparison categories:

  * new failures
  * corrected tests
  * still failing tests
  * regressed tests
  * improved tests

---

## Makefile workflow

Run these commands from the `verifcore/` directory.

The intended workflow is:

```bash
make demo
```

This rebuilds the full demo from scratch:

1. clean generated files
2. build the C++ parser
3. generate two synthetic regression logs
4. parse logs into JSONL
5. ingest JSONL into SQLite
6. run the analyzer report

Useful targets:

```bash
make build     # compile log_parser from cpp/*.cc
make generate-baseline    # create sample_logs/run_001.log
make generate-regression  # create sample_logs/run_002.log with injected regressions
make parse     # convert logs to parsed/*.jsonl using the C++ parser
make ingest    # load parsed JSONL into verifcore.db
make analyze   # print the terminal regression report
make test      # run pytest tests
make ui        # start the Streamlit dashboard
make demo      # clean -> build -> generate-baseline -> generate-regression -> parse -> ingest -> analyze
make clean     # remove generated demo artifacts
```

Generation defaults to 200 tests per run. Override it with `NUM_TESTS`:

```bash
make generate-baseline NUM_TESTS=1000
make generate-regression NUM_TESTS=1000
make demo NUM_TESTS=1000
```

`make clean` removes generated files only:

```text
log_parser
verifcore.db
parsed/*.jsonl
sample_logs/run_*.log
```

It intentionally keeps `sample_logs/manual.log`.

---

## Streamlit UI

The UI is a local dashboard on top of `verifcore.db`.

First build the demo data:

```bash
make demo
```

Install Streamlit into a local virtual environment if needed:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Then start the UI:

```bash
make ui
```

Streamlit prints a local URL such as:

```text
http://localhost:8501
```

The UI is a single results page with:

* a summary bar chart
* the main comparison table
* row search
* change-type filtering
* small visuals for the current search
* failure signature groups

The `all flagged` category is the union of rows worth triaging, including negative comparison changes and `status_changing` tests. `improved` is queryable as a filter, but it is not included in `all flagged`.

The search box is plain text search across table cells. It is not natural-language querying. Useful searches include:

```text
dma
seed=1000
sim_timeout
ASSERTION_FAILED
fifo_no_overflow
worker-3
```

---

## Manual workflow

If not using the Makefile, run the project manually:

```bash
# Build C++ parser
g++ -std=c++17 -Wall -Wextra -O2 cpp/*.cc -o log_parser

# Generate logs
python3 -m backend.generate_logs --out sample_logs/run_001.log --seed 1 --num-tests <count>
python3 -m backend.generate_logs --out sample_logs/run_002.log --seed 2 --num-tests <count> --inject-regressions

# Parse logs to JSONL
./log_parser sample_logs/run_001.log > parsed/run_001.jsonl
./log_parser sample_logs/run_002.log > parsed/run_002.jsonl

# Ingest JSONL into SQLite
rm -f verifcore.db
python3 -m backend.ingest --db verifcore.db --run-name run_001 --commit abc123 parsed/run_001.jsonl
python3 -m backend.ingest --db verifcore.db --run-name run_002 --commit def456 parsed/run_002.jsonl

# Analyze runs
python3 -m backend.analyze --db verifcore.db --baseline run_001 --current run_002

# Run tests
python3 -m pytest tests

# Start UI, after installing requirements into .venv
.venv/bin/python -m streamlit run ui/app.py --server.headless true
```

---

## Current limitations

VerifCore is a toy project.

Current limitations:

* It does not parse real simulator logs.
* It does not verify real RTL.
* Waveform paths are fake artifact paths.
* Failure types and assertions are synthetic.
* Performance metrics are generated, not measured from real hardware simulation.
* Flaky detection is approximate because true flakiness requires repeated runs under the same commit/configuration.
* The UI is local-only and reads from the generated SQLite database.

---

## Future work

Possible extensions:

* Add FastAPI endpoints for querying runs, failures, regressed tests, and improved tests.
* Add a React frontend for a more polished dashboard.
* Add support for uploaded log files.
* Add richer SQL queries for filtering by suite, assertion, failure type, or worker.
* Add run metadata such as branch, author, simulator version, and machine pool.
* Track artifact links and waveform paths in a clickable UI.
* Distinguish true flaky tests from real commit-to-commit status changes.
* Support multiple baselines and historical trends.
* Add latency/utilization charts.
* Add export to CSV or HTML reports.

---

## Summary

VerifCore demonstrates a miniature design-verification regression analysis workflow.

It starts with raw synthetic logs, parses them with a C++ streaming parser, serializes structured JSONL, stores results in SQLite, and compares regression runs to surface meaningful changes.

The goal is not to build a production DV platform. The goal is to show the core infrastructure pattern:

```text
raw logs -> structured records -> queryable database -> actionable regression report
```

That pattern is common across verification, infrastructure, CI systems, and large-scale engineering workflows.
