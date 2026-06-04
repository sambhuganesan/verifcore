from pathlib import Path
import sqlite3
import sys

import altair as alt
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import analyze  # noqa: E402


DEFAULT_DB_PATH = ROOT / "verifcore.db"


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
        padding-top: 1.4rem;
        padding-bottom: 2rem;
    }

    h1 {
        font-size: 1.8rem;
        margin-bottom: 0.1rem;
    }

    h2, h3 {
        margin-top: 1.4rem;
    }

    div[data-testid="stDataFrame"] {
        border: 1px solid #e5e7eb;
        border-radius: 6px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@st.cache_data
def load_runs(db_path):
    conn = connect(db_path)
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
def load_comparison(db_path, baseline_name, current_name):
    conn = analyze.db.connect(db_path)
    baseline_id = analyze.get_run_id(conn, baseline_name)
    current_id = analyze.get_run_id(conn, current_name)

    baseline_count = analyze.count_results(conn, baseline_id)
    current_count = analyze.count_results(conn, current_id)
    baseline_results = analyze.load_results(conn, baseline_id)
    current_results = analyze.load_results(conn, current_id)
    comparison = analyze.compare_runs(baseline_results, current_results)
    signature_groups = analyze.group_failure_signatures(current_results)
    flaky_tests = analyze.get_flaky_tests(conn)
    conn.close()

    return {
        "baseline_count": baseline_count,
        "current_count": current_count,
        "baseline_results": baseline_results,
        "current_results": current_results,
        "comparison": comparison,
        "signature_groups": signature_groups,
        "flaky_tests": flaky_tests,
    }


def test_id(record):
    return f'{record["suite"]}.{record["test_name"]} seed={record["seed"]}'


def result_key(record):
    return (record["suite"], record["test_name"], record["seed"])


def failure_signature(record):
    failure_type = record.get("failure_type")
    assertion = record.get("assertion_name")
    if not failure_type or failure_type == "none":
        return ""
    return f"{failure_type}:{assertion}"


def add_or_update_diff(rows_by_key, tag, baseline, current):
    source = current or baseline
    key = result_key(source)

    if key not in rows_by_key:
        rows_by_key[key] = {
            "change": [],
            "test": test_id(source),
            "suite": source["suite"],
            "baseline status": baseline["status"] if baseline else "",
            "current status": current["status"] if current else "",
            "baseline cycles": baseline["cycles"] if baseline else "",
            "current cycles": current["cycles"] if current else "",
            "delta cycles": "",
            "delta %": "",
            "current failure": failure_signature(current) if current else "",
            "worker": current["worker_id"] if current else source["worker_id"],
            "artifact": current["artifact_path"] if current else "",
        }

    if tag not in rows_by_key[key]["change"]:
        rows_by_key[key]["change"].append(tag)

    if baseline and current:
        delta = current["cycles"] - baseline["cycles"]
        pct = (delta / baseline["cycles"]) * 100
        rows_by_key[key]["delta cycles"] = delta
        rows_by_key[key]["delta %"] = round(pct, 1)


def build_diff_rows(data):
    rows_by_key = {}
    baseline_results = data["baseline_results"]
    current_results = data["current_results"]
    comparison = data["comparison"]

    for current in comparison["new_failures"]:
        baseline = baseline_results[result_key(current)]
        add_or_update_diff(rows_by_key, "new failure", baseline, current)

    for current in comparison["fixed_tests"]:
        baseline = baseline_results[result_key(current)]
        add_or_update_diff(rows_by_key, "fixed", baseline, current)

    for current in comparison["still_failing"]:
        baseline = baseline_results[result_key(current)]
        add_or_update_diff(rows_by_key, "still failing", baseline, current)

    for baseline, current in comparison["perf_regressions"]:
        add_or_update_diff(rows_by_key, "perf regression", baseline, current)

    for current in comparison["infra_failures"]:
        baseline = baseline_results.get(result_key(current))
        add_or_update_diff(rows_by_key, "infra failure", baseline, current)

    rows = []
    for row in rows_by_key.values():
        row["change"] = ", ".join(row["change"])
        rows.append(row)

    return sorted(rows, key=lambda row: (row["suite"], row["test"]))


def current_run_rows(current_results):
    rows = []
    for record in current_results.values():
        rows.append(
            {
                "test": test_id(record),
                "suite": record["suite"],
                "status": record["status"],
                "cycles": record["cycles"],
                "expected cycles": record["expected_cycles"],
                "failure": failure_signature(record),
                "worker": record["worker_id"],
                "artifact": record["artifact_path"],
            }
        )
    return sorted(rows, key=lambda row: (row["status"] != "FAIL", row["suite"], row["test"]))


def flaky_rows(flaky_tests):
    return [
        {
            "test": f'{row["suite"]}.{row["test_name"]} seed={row["seed"]}',
            "statuses": row["statuses"],
            "observations": row["observations"],
        }
        for row in flaky_tests
    ]


def count_by_field(rows, field):
    counts = {}
    for row in rows:
        value = row.get(field) or "none"
        counts[value] = counts.get(value, 0) + 1

    return [
        {field: value, "count": count}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def count_changes(rows):
    counts = {}
    for row in rows:
        for change in row["change"].split(", "):
            counts[change] = counts.get(change, 0) + 1

    return [
        {"change": change, "count": count}
        for change, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def filter_rows(rows, search_text):
    search_text = search_text.strip().lower()
    if not search_text:
        return rows

    filtered = []
    for row in rows:
        haystack = " ".join(str(value).lower() for value in row.values())
        if search_text in haystack:
            filtered.append(row)
    return filtered


def render_table(rows, search_text, empty_text):
    visible_rows = filter_rows(rows, search_text)
    st.caption(f"{len(visible_rows)} rows shown, {len(rows)} total")
    if visible_rows:
        st.dataframe(visible_rows, width="stretch", hide_index=True, height=520)
    else:
        st.info(empty_text)


def change_count_rows(comparison, flaky_count):
    return [
        {"change": "new failure", "count": len(comparison["new_failures"])},
        {"change": "fixed", "count": len(comparison["fixed_tests"])},
        {"change": "still failing", "count": len(comparison["still_failing"])},
        {"change": "perf regression", "count": len(comparison["perf_regressions"])},
        {"change": "infra failure", "count": len(comparison["infra_failures"])},
        {"change": "status_changing", "count": flaky_count},
    ]


def signature_rows(signature_groups):
    return [
        {"signature": signature, "count": count}
        for signature, count in signature_groups
    ]


def horizontal_bar_chart(rows, label_field, value_field, title, height=300):
    if not rows:
        st.info(f"No data for {title.lower()}.")
        return

    chart = (
        alt.Chart(alt.Data(values=rows))
        .mark_bar(color="#60a5fa")
        .encode(
            x=alt.X(
                f"{value_field}:Q",
                title="count",
                axis=alt.Axis(tickMinStep=1),
            ),
            y=alt.Y(
                f"{label_field}:N",
                title=None,
                sort="-x",
                axis=alt.Axis(labelLimit=420),
            ),
            tooltip=[
                alt.Tooltip(f"{label_field}:N", title=label_field),
                alt.Tooltip(f"{value_field}:Q", title=value_field),
            ],
        )
        .properties(height=height)
    )

    labels = (
        alt.Chart(alt.Data(values=rows))
        .mark_text(align="left", baseline="middle", dx=4, color="#374151")
        .encode(
            x=alt.X(f"{value_field}:Q"),
            y=alt.Y(f"{label_field}:N", sort="-x"),
            text=alt.Text(f"{value_field}:Q"),
        )
    )

    st.altair_chart(chart + labels, width="stretch")


def donut_chart(rows, label_field, value_field, title, height=260):
    if not rows:
        st.info(f"No data for {title.lower()}.")
        return

    chart = (
        alt.Chart(alt.Data(values=rows))
        .mark_arc(innerRadius=58, outerRadius=105)
        .encode(
            theta=alt.Theta(f"{value_field}:Q", title=value_field),
            color=alt.Color(
                f"{label_field}:N",
                title=None,
                scale=alt.Scale(
                    range=[
                        "#2563eb",
                        "#16a34a",
                        "#dc2626",
                        "#f59e0b",
                        "#7c3aed",
                        "#0891b2",
                    ]
                ),
            ),
            tooltip=[
                alt.Tooltip(f"{label_field}:N", title=label_field),
                alt.Tooltip(f"{value_field}:Q", title=value_field),
            ],
        )
        .properties(height=height)
    )

    st.altair_chart(chart, width="stretch")


def render_filtered_visuals(diff_rows, current_rows):
    st.subheader("Visual summary for current search")

    left, right, third = st.columns(3)
    with left:
        st.write("Current pass/fail")
        donut_chart(
            count_by_field(current_rows, "status"),
            "status",
            "count",
            "Current pass/fail",
        )

    with right:
        st.write("Change mix")
        donut_chart(
            count_changes(diff_rows),
            "change",
            "count",
            "Change mix",
        )

    with third:
        st.write("Top suites")
        horizontal_bar_chart(
            count_by_field(current_rows, "suite")[:8],
            "suite",
            "count",
            "Top suites",
            height=230,
        )


def render_summary_chart(change_rows):
    ordered_rows = [
        row
        for name in [
            "new failure",
            "fixed",
            "still failing",
            "perf regression",
            "infra failure",
            "status_changing",
        ]
        for row in change_rows
        if row["change"] == name
    ]
    horizontal_bar_chart(
        ordered_rows,
        "change",
        "count",
        "Summary",
        height=220,
    )


def render_results_page(data, comparison, baseline_name, current_name):
    st.write(f"**{baseline_name}** -> **{current_name}**")

    change_rows = change_count_rows(comparison, len(data["flaky_tests"]))
    st.subheader("Summary")
    render_summary_chart(change_rows)

    st.subheader("Comparison table")
    st.caption(
        "Search is a plain text match across table cells. "
        "Try values like `dma`, `sim_timeout`, `ASSERTION_FAILED`, or `seed=1000`."
    )
    search_text = st.text_input(
        "Search rows",
        placeholder="suite, test name, seed, assertion, failure type, worker...",
        label_visibility="collapsed",
    )
    diff_rows = build_diff_rows(data)
    category_options = [
        "all changes",
        "new failure",
        "fixed",
        "still failing",
        "perf regression",
        "infra failure",
    ]
    category = st.segmented_control(
        "Change type",
        category_options,
        default="all changes",
    )

    if category != "all changes":
        diff_rows = [row for row in diff_rows if category in row["change"]]

    render_table(
        diff_rows,
        search_text,
        "No rows match this search and change type.",
    )

    visible_diff_rows = filter_rows(diff_rows, search_text)
    visible_current_rows = filter_rows(
        current_run_rows(data["current_results"]),
        search_text,
    )
    render_filtered_visuals(visible_diff_rows, visible_current_rows)

    with st.expander("All current run results"):
        render_table(
            current_run_rows(data["current_results"]),
            search_text,
            "No current-run rows match this search.",
        )

    with st.expander("status_changing tests"):
        render_table(
            flaky_rows(data["flaky_tests"]),
            search_text,
            "No status_changing tests match this search.",
        )


def render_graphs_page(data, comparison, baseline_name, current_name):
    st.write(f"**{baseline_name}** -> **{current_name}**")
    st.caption(
        "Use the search box to graph one subset, for example `dma`, "
        "`sim_timeout`, `ASSERTION_FAILED`, or `seed=1000`."
    )

    change_rows = change_count_rows(comparison, len(data["flaky_tests"]))
    sig_rows = signature_rows(data["signature_groups"])
    diff_rows = build_diff_rows(data)
    all_current_rows = current_run_rows(data["current_results"])

    graph_search = st.text_input(
        "Graph search",
        placeholder="suite, test name, seed, assertion, failure type, worker...",
    )
    filtered_diff_rows = filter_rows(diff_rows, graph_search)
    filtered_current_rows = filter_rows(all_current_rows, graph_search)

    st.subheader("Filtered subset")
    st.caption(
        f"{len(filtered_current_rows)} current-run tests and "
        f"{len(filtered_diff_rows)} changed tests match this search."
    )
    render_filtered_visuals(filtered_diff_rows, filtered_current_rows)

    st.subheader("Change counts")
    horizontal_bar_chart(change_rows, "change", "count", "Change counts", height=260)

    st.subheader("Failure signatures")
    horizontal_bar_chart(sig_rows, "signature", "count", "Failure signatures", height=280)

    left, right = st.columns(2)
    with left:
        st.write("Change count data")
        st.dataframe(change_rows, width="stretch", hide_index=True)

    with right:
        st.write("Failure signature data")
        if sig_rows:
            st.dataframe(sig_rows, width="stretch", hide_index=True)
        else:
            st.info("No failures in the current run.")


def main():
    st.title("VerifCore")
    st.caption("Compare two regression runs from the SQLite database.")

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
        page = st.radio("Page", ["Results", "Graphs"], horizontal=False)

        st.divider()
        st.caption("Selected runs")
        for run in runs:
            if run["run_name"] in {baseline_name, current_name}:
                st.write(f'`{run["run_name"]}` · `{run["commit_hash"]}`')

        if st.button("Refresh", width="stretch"):
            st.cache_data.clear()
            st.rerun()

    if baseline_name == current_name:
        st.warning("Choose two different runs.")
        return

    data = load_comparison(str(db_file), baseline_name, current_name)
    comparison = data["comparison"]

    if page == "Results":
        render_results_page(data, comparison, baseline_name, current_name)
    else:
        render_graphs_page(data, comparison, baseline_name, current_name)


if __name__ == "__main__":
    main()
