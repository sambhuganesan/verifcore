# VerifCore

VerifCore is a small C++/Python/SQLite project inspired by design verification
regression tooling.

The project takes synthetic DV-style regression logs, parses them into JSONL,
stores them in a normalized SQLite schema, and lets engineers compare one
reference run against one or more other runs through SQL-backed triage queries.

The goal is not to build a chatbot or a production DV platform. The goal is to
show the core infrastructure pattern:

```text
raw logs -> structured records -> relational database -> SQL triage UI
```

## Quick Start

The intended public demo is a hosted Streamlit app with a preloaded SQLite
database. Visitors should be able to open one link and immediately compare four
synthetic regression runs with 1000 tests each.

The hosted app loads:

```text
data/verifcore_demo.db
```

That database is checked into the repo so the UI can run without compiling the
C++ parser or generating logs at startup.

From the `verifcore/` directory:

```bash
make demo
```

This builds the C++ parser, generates demo runs, parses them into JSONL, ingests
them into SQLite, and prints the terminal regression report.

With no overrides, `make demo` uses `NUM_TESTS=1000` and `NUM_RUNS=4`. That
creates `run_001` through `run_004`, each with 1000 tests, for 4000 total
`test_results` rows. `run_001` is generated without injected changes, and
`run_002...run_004` are generated with injected changes. The terminal report
compares `run_001` against `run_002`.

Use `NUM_TESTS` to control tests per run and `NUM_RUNS` to control total runs.
When `NUM_RUNS` is greater than 2, `run_002...run_N` are generated with
injected changes.

To install Python dependencies and launch the local UI:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
make ui
```

`requirements.txt` includes Streamlit for the UI and pytest for the test suite.
Then open the Streamlit URL printed in the terminal, usually:

```text
http://localhost:8501
```

## What VerifCore Answers

VerifCore compares regression runs and helps answer questions such as:

* Which tests are newly failing?
* Which tests were fixed?
* Which tests are still failing?
* Which tests slowed down?
* Which compared-run failures have VCD paths?
* Which failures came from a specific suite or worker?
* Which assertion or failure type is involved?
* Which compared tests changed cycles by at least a chosen percentage?
* How does one reference run compare against selected other runs?
* Which compared run introduced the most new failures or slowdowns?

The UI exposes these as a query form backed by parameterized SQL, not natural
language.

## High-Level Pipeline

```text
synthetic DV logs
    -> C++ streaming parser
    -> JSONL test records
    -> normalized SQLite ingestion
    -> SQL comparison layer
    -> terminal report and Streamlit query UI
```

The same SQLite database powers the terminal report and the Streamlit UI.

## Project Structure

```text
verifcore/
├── README.md
├── Makefile
├── requirements.txt
├── cpp/
│   ├── main.cc
│   ├── line_reader.*
│   ├── line_classifier.*
│   ├── kv_parser.*
│   ├── record_parser.*
│   ├── string_utils.*
│   └── test_result.*
├── backend/
│   ├── generate_logs.py
│   ├── db.py
│   ├── ingest.py
│   ├── analyze.py
│   └── triage_sql.py
├── data/
│   └── verifcore_demo.db
├── docs/
│   └── sql_regression_model.md
├── ui/
│   └── app.py
├── sample_logs/
├── parsed/
└── tests/
    ├── test_analysis.py
    └── test_triage_sql.py
```

## Synthetic Log Format

VerifCore uses a small fake DV-style log format. One log file represents one
regression run. Each test result is represented by a block of lines.

A passing test:

```text
[RUN] suite=dma test=aligned_burst_0 seed=1000 worker=worker-0
[METRIC] cycles=684 expected_cycles=700 utilization=0.8
[PASS]
```

A failing test:

```text
[RUN] suite=systolic_array test=backpressure_13 seed=1013 worker=worker-5
[METRIC] cycles=1035 expected_cycles=1025 utilization=0.72
[FAIL] type=ASSERTION_FAILED assertion=fifo_no_overflow artifact=waves/systolic_array_backpressure_13_seed1013.vcd
```

Each record contains:

| Field | Meaning |
| --- | --- |
| `suite` | Logical area such as `dma`, `cache`, or `systolic_array` |
| `test` / `test_name` | Test name within the suite |
| `seed` | Deterministic random seed |
| `worker` / `worker_id` | Fake worker that ran the test |
| `cycles` | Actual simulated hardware cycles taken |
| `expected_cycles` | Expected cycle count |
| `utilization` | Synthetic utilization metric |
| `status` | `PASS` or `FAIL` |
| `type` / `failure_type` | `ASSERTION_FAILED` or `INFRA_FAILURE` |
| `assertion` / `assertion_name` | Specific failure signature |
| `artifact` / `vcd_path` | Fake waveform path |

The stable identity of a test is:

```text
suite + test_name + seed
```

That identity is what lets VerifCore compare the same logical test across
different runs.

## DV Concepts Used

A **clock cycle** is one simulated hardware clock tick. It is not wall-clock
time.

A **waveform file**, such as a `.vcd`, records signal values over simulated
time. In this project, VCD paths are fake artifact paths used for realism.

An **assertion failure** means the design violated a rule that the test expected
to hold.

An **infrastructure failure** means the failure may not be caused by the design
itself. Examples include simulator timeout, worker failure, environment issue,
or missing artifact.

Generated suites:

| Suite | Meaning |
| --- | --- |
| `dma` | Direct Memory Access logic |
| `systolic_array` | Matrix/AI accelerator compute fabric |
| `cache` | Cache behavior |
| `noc` | Network-on-chip routing |
| `decoder` | Packet or instruction decode logic |

Generated test families:

| Test family | Meaning |
| --- | --- |
| `aligned_burst` | Burst memory transfer with aligned addresses |
| `backpressure` | Valid/ready flow control under downstream stalls |
| `randomized_smoke` | Broad randomized sanity test |
| `reset_recovery` | Behavior after reset is asserted and released |
| `protocol_stress` | Heavy protocol-level traffic |

Failure signatures:

| Failure type | Assertion | Meaning |
| --- | --- | --- |
| `ASSERTION_FAILED` | `valid_ready_protocol` | Valid/ready handshake rule was violated |
| `ASSERTION_FAILED` | `fifo_no_overflow` | FIFO overflow rule was violated |
| `ASSERTION_FAILED` | `reset_clears_state` | Reset did not clear expected state |
| `ASSERTION_FAILED` | `packet_ordering` | Packets came out in the wrong order |
| `INFRA_FAILURE` | `sim_timeout` | Simulator timed out |

## C++ Parser

The C++ parser reads raw log files and writes one JSON object per test result.

Build:

```bash
make build
```

Parse logs:

```bash
./log_parser sample_logs/run_001.log > parsed/run_001.jsonl
./log_parser sample_logs/run_002.log > parsed/run_002.jsonl
```

Parser components:

| Component | Responsibility |
| --- | --- |
| `line_reader` | Reads bytes, handles arbitrary chunks, splits lines |
| `line_classifier` | Classifies lines as `RUN`, `METRIC`, `PASS`, `FAIL`, or `UNKNOWN` |
| `kv_parser` | Parses `key=value` fields |
| `record_parser` | Builds complete `TestResult` records |
| `test_result` | Stores fields and serializes JSON |

Example JSONL output:

```json
{"suite":"dma","test_name":"aligned_burst_0","seed":1000,"worker_id":"worker-0","cycles":684,"expected_cycles":700,"utilization":0.8,"status":"FAIL","failure_type":"ASSERTION_FAILED","assertion_name":"valid_ready_protocol","artifact_path":"waves/dma_aligned_burst_0_seed1000.vcd"}
```

## SQLite Ingestion

The ingestion layer stores parsed records in SQLite.

```bash
python3 -m backend.ingest \
  --db verifcore.db \
  --run-name run_001 \
  --commit commit_001 \
  parsed/run_001.jsonl
```

Ingestion normalizes each JSONL record into:

* `test_cases`
* `failure_signatures`
* `test_results`

Passing tests have no failure signature. Failing tests reference a reusable
failure signature.

## Database Schema

VerifCore uses four core tables:

```text
runs
test_cases
failure_signatures
test_results
```

Relationship model:

```text
runs 1 ─── * test_results * ─── 1 test_cases
                  |
                  * ─── 0/1 failure_signatures
```

`test_results` is the central fact table. Each row means:

```text
in this run, this stable test case produced this result
```

Worker name and VCD path stay directly on `test_results` for now because they
are simple queryable fields in this project.

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

### `failure_signatures`

```sql
CREATE TABLE failure_signatures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    failure_type TEXT NOT NULL,
    assertion_name TEXT NOT NULL,
    UNIQUE(failure_type, assertion_name)
);
```

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

For the default demo of four runs with 1000 tests each:

```text
runs:                 4 rows
test_cases:        1000 rows
test_results:      4000 rows
failure_signatures: reused debug buckets
```

## SQL Views And Query Layer

The normalized schema is good for integrity, but analysis often wants a flat
row shape. VerifCore creates a SQL view named `result_details`:

```text
result_details =
test_results
JOIN test_cases
LEFT JOIN failure_signatures
```

It exposes convenient columns such as:

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

The pairwise comparison query is a self-join through stable test identity:

```sql
WITH regression_comparison AS (
    SELECT ...
    FROM result_details b
    JOIN result_details c
      ON b.suite = c.suite
     AND b.test_name = c.test_name
     AND b.seed = c.seed
    WHERE b.run_id = ?
      AND c.run_id = ?
)
```

`backend/triage_sql.py` builds parameterized SQL queries over that comparison
relation. The UI does not concatenate user text into SQL.

For run-level history, `compare_run_to_many` compares one reference run against
selected other runs and returns one summary row per compared run:

```text
compared_run | commit_hash | created_at | compared_tests | new_failures | fixed_tests | still_failing | slower_tests | infra_failures
```

This is where `runs.commit_hash` and `runs.created_at` become useful: they make
each compared run identifiable and sortable as part of a run history.

Supported pairwise query kinds:

| UI question | Meaning |
| --- | --- |
| `New failures` | Reference run passed, compared run failed |
| `Current failures` | Compared result is `FAIL` |
| `Fixed tests` | Reference run failed, compared run passed |
| `Still failing` | Failed in both reference and compared runs |
| `Slowed down` | Compared cycles increased enough versus reference |
| `Failures with VCDs` | Compared-run failures that have a VCD path |
| `All compared tests` | All matched tests between the two runs |

Supported filters:

| Filter | Notes |
| --- | --- |
| `Suite` | Values come from the compared run |
| `Worker` | Values come from the compared run |
| `Failure type` | Values come from compared-run failures |
| `Assertion` | Values come from compared-run failures |
| `Minimum cycle change %` | Float from `-100` to `100`; blank means no filter |
| `Row limit` | Limits returned rows |

The pairwise result table keeps `seed` as its own column. In this table,
`baseline` means the selected reference run and `current` means the selected
compared run:

```text
suite | test | seed | baseline | current | failure | cycle change % | worker | vcd
```

## Streamlit UI

The UI is a SQL-backed query surface. By default, it loads the prebuilt demo
database:

```text
data/verifcore_demo.db
```

If that file is missing, the app falls back to the locally generated
`verifcore.db`. The sidebar keeps the SQLite database path under an advanced
control for local development.

Start it with:

```bash
make ui
```

The page has:

* reference-run selection
* a `Compare to` multiselect
* query-aware metrics above the form
* pairwise query filters for suite, worker, failure type, assertion, and cycle change
* result tables backed by parameterized SQL

The `Compare to` selection controls the view:

| Selection | UI behavior |
| --- | --- |
| One compared run | Show the detailed pairwise query builder |
| Multiple compared runs | Show one summary row per compared run |

The top metrics update with the active query and filters:

```text
Rows
Current failures
New failures
Fixed
Slower
Infra
```

Example UI queries:

```text
Question: Current failures
Suite: dma
Worker: Any
Failure type: ASSERTION_FAILED
```

```text
Question: Slowed down
Minimum cycle change %: 20
```

```text
Question: Failures with VCDs
Suite: cache
```

Example run-history query:

```text
Reference run: run_002
Compare to: run_003, run_004
```

This produces one row per selected compared run, including commit hash, created time, new
failures, fixed tests, still-failing tests, slower tests, and infra failures.

## Terminal Analyzer

The terminal analyzer still prints a compact regression report:

```bash
python3 -m backend.analyze \
  --db verifcore.db \
  --baseline run_001 \
  --current run_002
```

It reports:

* new failures
* corrected tests
* still-failing tests
* slowed-down tests
* improved tests
* infrastructure failures
* failure signature groups
* `status_changing` tests

Example output:

```text
VerifCore Regression Report
===========================
Baseline run_001: 1000 tests
Current  run_002: 1000 tests

Summary
-------
New failures: 19
Corrected tests: 7
Still failing: 9
Slowed down: 10
Improved: 90
Infra failures: 9
status_changing: 26
```

## Makefile Workflow

Useful targets:

```bash
make build                # compile C++ parser
make generate-baseline    # create sample_logs/run_001.log
make generate-regression  # create sample_logs/run_002.log with injected changes
make generate-runs        # create run_001 through run_N using NUM_RUNS
make parse                # convert logs to parsed/*.jsonl
make ingest               # load parsed JSONL into verifcore.db
make analyze              # print terminal report
make test                 # run pytest tests
make ui                   # start Streamlit UI
make demo                 # clean -> build -> generate -> parse -> ingest -> analyze
make demo-db              # regenerate data/verifcore_demo.db
make clean                # remove generated demo artifacts
```

`make demo` with no overrides is equivalent to:

```bash
make demo NUM_TESTS=1000 NUM_RUNS=4
```

That default creates four runs and 4000 total `test_results` rows. Override with:

```bash
make demo NUM_TESTS=200 NUM_RUNS=2
make demo NUM_TESTS=500 NUM_RUNS=6
```

With `NUM_RUNS=4`, VerifCore creates:

```text
run_001  commit_001  reference-style run
run_002  commit_002  compared run with injected changes
run_003  commit_003  compared run with injected changes
run_004  commit_004  compared run with injected changes
```

`make clean` removes generated files only:

```text
log_parser
verifcore.db
parsed/*.jsonl
sample_logs/run_*.log
```

It intentionally keeps `sample_logs/manual.log`.

`make demo-db` refreshes the checked-in hosted demo database. It runs the normal
demo flow, then copies `verifcore.db` to `data/verifcore_demo.db`.

## Free Hosting

The simplest free deployment path is Streamlit Community Cloud:

```text
Repository: this repo on GitHub
Entrypoint: ui/app.py
Dependencies: requirements.txt
Demo data: data/verifcore_demo.db
```

After deployment, the public README can include the hosted URL and a GIF showing
the run selector, query filters, and result table.

## Manual Workflow

```bash
# Build parser
g++ -std=c++17 -Wall -Wextra -O2 cpp/*.cc -o log_parser

# Generate logs. Repeat the injected command with more seeds for more runs.
python3 -m backend.generate_logs --out sample_logs/run_001.log --seed 1 --num-tests 200
python3 -m backend.generate_logs --out sample_logs/run_002.log --seed 2 --num-tests 200 --inject-regressions
python3 -m backend.generate_logs --out sample_logs/run_003.log --seed 3 --num-tests 200 --inject-regressions

# Parse logs
mkdir -p parsed
./log_parser sample_logs/run_001.log > parsed/run_001.jsonl
./log_parser sample_logs/run_002.log > parsed/run_002.jsonl
./log_parser sample_logs/run_003.log > parsed/run_003.jsonl

# Ingest into SQLite
rm -f verifcore.db
python3 -m backend.ingest --db verifcore.db --run-name run_001 --commit commit_001 parsed/run_001.jsonl
python3 -m backend.ingest --db verifcore.db --run-name run_002 --commit commit_002 parsed/run_002.jsonl
python3 -m backend.ingest --db verifcore.db --run-name run_003 --commit commit_003 parsed/run_003.jsonl

# Analyze
python3 -m backend.analyze --db verifcore.db --baseline run_001 --current run_002

# Test
.venv/bin/python -m pytest tests

# UI
.venv/bin/python -m streamlit run ui/app.py --server.headless true
```

## Tests

Run:

```bash
.venv/bin/python -m pytest tests
```

The tests cover:

* pass/fail comparison categories
* slowdown and improvement detection
* failure signature grouping
* normalized schema uniqueness
* SQL comparison rows
* one-reference-to-many-runs comparison summaries
* query filtering by suite, worker, failure type, assertion, and cycle change
* queryable filter value discovery
* rejection of unsupported query kinds

## Current Limitations

VerifCore is intentionally small.

Current limitations:

* It uses synthetic logs, not real simulator output.
* It does not verify real RTL.
* VCD paths are fake artifact paths.
* Failure types and assertions are synthetic.
* Cycle counts are generated, not measured from real simulation.
* `status_changing` is approximate because true flakiness requires repeated runs under the same commit/configuration.
* The UI is local-only.
* The query UI is controlled filters, not natural-language search.

## Future Work

Possible extensions:

* Add historical trend queries across many runs.
* Add branch, author, simulator version, or machine metadata.
* Add export to CSV or HTML reports.
* Add clickable artifact handling for real VCD/log paths.
* Add richer grouping queries for suite, assertion, worker, and test family.
* Add a true flakiness model using repeated runs under the same commit.

## Summary

VerifCore demonstrates a miniature design-verification regression analysis
workflow.

It starts with raw synthetic logs, parses them with a C++ streaming parser,
serializes structured JSONL, stores normalized records in SQLite, and uses SQL
queries to compare regression runs.

The important idea is:

```text
stable test identities + normalized results + SQL comparison queries
```

That pattern is common across verification, CI systems, infrastructure
monitoring, and large-scale engineering workflows.
