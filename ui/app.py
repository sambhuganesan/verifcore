from pathlib import Path
import sys

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import db, triage_sql  # noqa: E402


DEFAULT_DB_PATH = ROOT / "verifcore.db"
QUERY_OPTIONS = {
    "New failures": "new_failures",
    "Current failures": "current_failures",
    "Fixed tests": "fixed",
    "Still failing": "still_failing",
    "Slowed down": "slowed_down",
    "Failures with VCDs": "vcds",
    "All compared tests": "all",
}


st.set_page_config(
    page_title="VerifCore",
    page_icon="VC",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.25rem;
        padding-bottom: 2rem;
    }

    h1 {
        font-size: 1.75rem;
        margin-bottom: 0.1rem;
    }

    h2, h3 {
        margin-top: 1.1rem;
    }

    div[data-testid="stMetric"] {
        border: 1px solid #e5e7eb;
        border-radius: 6px;
        padding: 0.65rem 0.8rem;
        background: #ffffff;
    }

    div[data-testid="stDataFrame"] {
        border: 1px solid #e5e7eb;
        border-radius: 6px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def load_runs(db_path):
    conn = db.connect(db_path)
    conn.row_factory = _row_factory
    rows = conn.execute(
        """
        SELECT id, run_name, commit_hash, created_at
        FROM runs
        ORDER BY id
        """
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


@st.cache_data
def load_triage(db_path, baseline_name, current_name):
    conn = db.connect(db_path)
    conn.row_factory = _row_factory

    baseline_id = get_run_id(conn, baseline_name)
    current_id = get_run_id(conn, current_name)

    data = {
        "baseline_id": baseline_id,
        "current_id": current_id,
        "baseline_count": count_results(conn, baseline_id),
        "current_count": count_results(conn, current_id),
        "summary": triage_sql.summarize_comparison(conn, baseline_id, current_id),
        "filters": triage_sql.filter_values(conn, current_id),
    }

    conn.close()
    return data


@st.cache_data
def run_query(
    db_path,
    baseline_id,
    current_id,
    query_kind,
    suite,
    worker,
    failure_type,
    assertion,
    min_cycle_change_pct,
    limit,
):
    conn = db.connect(db_path)
    conn.row_factory = _row_factory
    rows = triage_sql.query_comparison(
        conn,
        baseline_id,
        current_id,
        query_kind=query_kind,
        suite=suite,
        worker=worker,
        failure_type=failure_type,
        assertion=assertion,
        min_cycle_change_pct=min_cycle_change_pct,
        limit=limit,
    )
    conn.close()
    return rows


def _row_factory(cursor, row):
    return {
        column[0]: row[index]
        for index, column in enumerate(cursor.description)
    }


def get_run_id(conn, run_name):
    row = conn.execute(
        """
        SELECT id
        FROM runs
        WHERE run_name = ?
        """,
        (run_name,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown run: {run_name}")
    return row["id"]


def count_results(conn, run_id):
    return conn.execute(
        """
        SELECT COUNT(*) AS result_count
        FROM test_results
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()["result_count"]


def metric_grid(rows):
    cols = st.columns(6)
    metrics = query_metrics(rows)
    for col, (label, value) in zip(cols, metrics):
        col.metric(label, value)


def query_metrics(rows):
    return [
        ("Rows", len(rows)),
        (
            "Current failures",
            sum(1 for row in rows if row["current_status"] == "FAIL"),
        ),
        (
            "New failures",
            sum(1 for row in rows if row["status_change_type"] == "new_failure"),
        ),
        (
            "Fixed",
            sum(1 for row in rows if row["status_change_type"] == "fixed"),
        ),
        (
            "Slower",
            sum(1 for row in rows if row["perf_change_type"] == "perf_regression"),
        ),
        (
            "Infra",
            sum(1 for row in rows if row["is_infra_failure"]),
        ),
    ]


def comparison_rows(rows):
    return [
        {
            "suite": row["suite"],
            "test": row["test_name"],
            "seed": row["seed"],
            "baseline": row["baseline_status"],
            "current": row["current_status"],
            "failure": row["failure_signature"] if row["failure_type"] != "none" else "",
            "cycle change %": row["cycle_change_pct"],
            "worker": row["current_worker_id"],
            "vcd": row["artifact_path"],
        }
        for row in rows
    ]


def dataframe(rows, height=360):
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True, height=height)
    else:
        st.info("No rows for this query.")


def selected_filter(label, options):
    values = ["Any", *options]
    selected = st.selectbox(label, values)
    if selected == "Any":
        return None
    return selected


def parse_cycle_threshold(raw_value):
    value = raw_value.strip()
    if not value:
        return None, None

    try:
        threshold = float(value)
    except ValueError:
        return None, "Cycle change must be a number between -100 and 100."

    if threshold < -100 or threshold > 100:
        return None, "Cycle change must be between -100 and 100."

    return threshold, None


def render_query_builder(db_path, data, metric_slot):
    st.subheader("Query")

    top_left, top_right = st.columns([2, 1])
    with top_left:
        question_label = st.selectbox("Question", list(QUERY_OPTIONS.keys()))
    with top_right:
        limit = st.number_input("Row limit", min_value=10, max_value=1000, value=200, step=10)

    filters = data["filters"]
    col_suite, col_worker, col_failure, col_assertion = st.columns(4)
    with col_suite:
        suite = selected_filter("Suite", filters["suites"])
    with col_worker:
        worker = selected_filter("Worker", filters["workers"])
    with col_failure:
        failure_type = selected_filter("Failure type", filters["failure_types"])
    with col_assertion:
        assertion = selected_filter("Assertion", filters["assertions"])

    query_kind = QUERY_OPTIONS[question_label]
    raw_threshold = st.text_input(
        "Minimum cycle change %",
        value="20" if query_kind == "slowed_down" else "",
        placeholder="-100 to 100",
    )
    min_cycle_change_pct, threshold_error = parse_cycle_threshold(raw_threshold)

    if threshold_error:
        st.error(threshold_error)
        rows = []
    else:
        rows = run_query(
            str(db_path),
            data["baseline_id"],
            data["current_id"],
            query_kind,
            suite,
            worker,
            failure_type,
            assertion,
            min_cycle_change_pct,
            int(limit),
        )

    chips = [question_label]
    for label, value in [
        ("suite", suite),
        ("worker", worker),
        ("failure type", failure_type),
        ("assertion", assertion),
    ]:
        if value:
            chips.append(f"{label}: {value}")
    if min_cycle_change_pct is not None:
        chips.append(f"cycle change >= {min_cycle_change_pct}%")

    with metric_slot:
        metric_grid(rows)

    st.caption("Query: " + " | ".join(chips))
    dataframe(comparison_rows(rows), height=460)


def render_dashboard(db_path, data):
    metric_slot = st.container()
    render_query_builder(db_path, data, metric_slot)


def main():
    st.title("VerifCore")
    st.caption("SQL-backed regression triage")

    with st.sidebar:
        st.header("Runs")
        db_path = st.text_input("Database path", value=str(DEFAULT_DB_PATH))

        db_file = Path(db_path)
        if not db_file.exists():
            st.error("Database not found. Run `make demo` from `verifcore` first.")
            return

        runs = load_runs(str(db_file))
        if len(runs) < 2:
            st.error("Need at least two ingested runs to compare.")
            return

        run_names = [run["run_name"] for run in runs]
        baseline_name = st.selectbox("Baseline run", run_names, index=0)
        current_name = st.selectbox("Current run", run_names, index=1)

        st.divider()
        st.caption("Selected commits")
        for run in runs:
            if run["run_name"] in {baseline_name, current_name}:
                st.write(f'`{run["run_name"]}` · `{run["commit_hash"]}`')

        if st.button("Refresh", width="stretch"):
            st.cache_data.clear()
            st.rerun()

    if baseline_name == current_name:
        st.warning("Choose two different runs.")
        return

    data = load_triage(str(db_file), baseline_name, current_name)
    st.write(
        f"**{baseline_name}** ({data['baseline_count']} tests) -> "
        f"**{current_name}** ({data['current_count']} tests)"
    )
    render_dashboard(str(db_file), data)


if __name__ == "__main__":
    main()
