import os
from pathlib import Path
import sys
from urllib.parse import urlencode
from uuid import uuid4

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import db, triage_sql  # noqa: E402


DEMO_DB_PATH = ROOT / "data" / "verifcore_demo.db"
LOCAL_DB_PATH = ROOT / "verifcore.db"
DEFAULT_GOATCOUNTER_CODE = "sganesan"
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


def config_value(name):
    if name in os.environ:
        return os.environ[name]

    try:
        return st.secrets.get(name)
    except FileNotFoundError:
        return None


def render_analytics_pixel():
    goatcounter_code = config_value("GOATCOUNTER_CODE") or DEFAULT_GOATCOUNTER_CODE
    if not goatcounter_code:
        return

    if st.session_state.get("analytics_tracked"):
        return

    st.session_state.analytics_tracked = True
    st.session_state.analytics_event_id = str(uuid4())

    params = urlencode(
        {
            "p": "/",
            "t": "VerifCore",
            "r": st.session_state.analytics_event_id,
        }
    )
    src = f"https://{goatcounter_code}.goatcounter.com/count?{params}"
    st.markdown(
        f"""
        <img
            src="{src}"
            alt=""
            width="1"
            height="1"
            aria-hidden="true"
            style="position:absolute;left:-9999px;top:auto;width:1px;height:1px;opacity:0;"
        />
        """,
        unsafe_allow_html=True,
    )


render_analytics_pixel()


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
def load_triage(db_path, reference_name, compared_name):
    conn = db.connect(db_path)
    conn.row_factory = _row_factory

    reference_id = get_run_id(conn, reference_name)
    compared_id = get_run_id(conn, compared_name)

    data = {
        "reference_id": reference_id,
        "compared_id": compared_id,
        "reference_count": count_results(conn, reference_id),
        "compared_count": count_results(conn, compared_id),
        "summary": triage_sql.summarize_comparison(conn, reference_id, compared_id),
        "filters": triage_sql.filter_values(conn, compared_id),
    }

    conn.close()
    return data


@st.cache_data
def load_many_run_comparison(db_path, reference_name, compared_names):
    conn = db.connect(db_path)
    conn.row_factory = _row_factory
    reference_id = get_run_id(conn, reference_name)
    compared_ids = [get_run_id(conn, run_name) for run_name in compared_names]
    rows = triage_sql.compare_run_to_many(conn, reference_id, compared_ids)
    reference_count = count_results(conn, reference_id)
    conn.close()
    return {
        "reference_id": reference_id,
        "reference_count": reference_count,
        "rows": rows,
    }


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


def default_db_path():
    if DEMO_DB_PATH.exists():
        return DEMO_DB_PATH
    return LOCAL_DB_PATH


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
            data["reference_id"],
            data["compared_id"],
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


def many_run_metrics(rows):
    cols = st.columns(6)
    metrics = [
        ("Runs", len(rows)),
        ("Compared tests", sum(row["compared_tests"] for row in rows)),
        ("New failures", sum(row["new_failures"] for row in rows)),
        ("Fixed", sum(row["fixed_tests"] for row in rows)),
        ("Slower", sum(row["slower_tests"] for row in rows)),
        ("Infra", sum(row["infra_failures"] for row in rows)),
    ]
    for col, (label, value) in zip(cols, metrics):
        col.metric(label, int(value or 0))


def render_many_run_comparison(data):
    many_run_metrics(data["rows"])
    dataframe(data["rows"], height=520)


def main():
    st.title("VerifCore")
    st.caption("SQL-backed regression triage")

    with st.sidebar:
        st.header("Runs")
        default_path = default_db_path()
        if default_path == DEMO_DB_PATH:
            st.caption("Dataset: preloaded demo database")
        else:
            st.caption("Dataset: local generated database")

        db_path = str(default_path)
        with st.expander("Advanced"):
            db_path = st.text_input("SQLite database path", value=db_path)

        db_file = Path(db_path)
        if not db_file.exists():
            st.error("Database not found. Run `make demo` locally or use the preloaded demo database.")
            return

        runs = load_runs(str(db_file))
        if len(runs) < 2:
            st.error("Need at least two ingested runs to compare.")
            return

        run_names = [run["run_name"] for run in runs]
        reference_name = st.selectbox("Reference run", run_names, index=0)
        compared_options = [run_name for run_name in run_names if run_name != reference_name]
        default_compared = compared_options[:1]
        compared_names = st.multiselect(
            "Compare to",
            compared_options,
            default=default_compared,
        )

        st.divider()
        st.caption("Selected commits")
        selected_names = {reference_name, *compared_names}
        for run in runs:
            if run["run_name"] in selected_names:
                st.write(f'`{run["run_name"]}` · `{run["commit_hash"]}`')

        if st.button("Refresh", width="stretch"):
            st.cache_data.clear()
            st.rerun()

    if not compared_names:
        st.warning("Choose at least one run to compare against the reference run.")
        return

    if len(compared_names) == 1:
        compared_name = compared_names[0]
        data = load_triage(str(db_file), reference_name, compared_name)
        st.write(
            f"**{reference_name}** ({data['reference_count']} tests) -> "
            f"**{compared_name}** ({data['compared_count']} tests)"
        )
        render_dashboard(str(db_file), data)
    else:
        data = load_many_run_comparison(str(db_file), reference_name, tuple(compared_names))
        st.write(
            f"Reference: **{reference_name}** ({data['reference_count']} tests)"
        )
        render_many_run_comparison(data)


if __name__ == "__main__":
    main()
