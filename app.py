import streamlit as st
import pandas as pd
import altair as alt
from datetime import date

from strava_client import StravaClient


# --------- PAGE CONFIG ---------
st.set_page_config(
    page_title="Strava Dashboard",
    page_icon="🏃",
    layout="wide",
)


# --------- LOAD DATA ---------
@st.cache_data(show_spinner=True)
def load_activities(max_activities: int = 1000) -> pd.DataFrame:
    cfg = st.secrets["strava"]
    client = StravaClient(
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
        refresh_token=cfg["refresh_token"],
    )

    raw = client.get_recent_activities(max_activities=max_activities)
    df = client.activities_to_df(raw)
    return df


# --------- SIDEBAR ---------
st.sidebar.title("⚙️ Settings")

with st.sidebar.expander("Strava import", expanded=True):
    max_acts = st.number_input(
        "Max number of activities to load",
        min_value=100,
        max_value=2000,
        value=1000,
        step=100,
    )
    reload_button = st.button("🔄 Reload data")

if "data" not in st.session_state or reload_button:
    with st.spinner("Loading activities from Strava..."):
        df = load_activities(max_activities=max_acts)
        st.session_state["data"] = df.copy()
else:
    df = st.session_state["data"].copy()

if df.empty:
    st.warning("No activities found. Check your API keys or increase max activities.")
    st.stop()

# Filters
sports = sorted(df["sport"].dropna().unique().tolist())
selected_sports = st.sidebar.multiselect(
    "Sports",
    options=sports,
    default=sports,
)

min_date = df["date"].min()
max_date = df["date"].max()

start_date, end_date = st.sidebar.date_input(
    "Date range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
)

if isinstance(start_date, tuple) or isinstance(start_date, list):
    # Safety if Streamlit returns a tuple for some reason
    start_date, end_date = start_date

# Apply filters
mask = (
    df["sport"].isin(selected_sports)
    & (df["date"] >= start_date)
    & (df["date"] <= end_date)
)

df_filt = df.loc[mask].copy()

st.sidebar.markdown("---")
st.sidebar.write(f"**Activities in view:** {len(df_filt)}")


# --------- HEADER ---------
st.title("🏃‍♂️ Strava Training Dashboard")
st.caption("Stylish analytics for your runs, rides, swims and more.")


# --------- TOP METRICS ---------
if df_filt.empty:
    st.warning("No activities for the selected filters.")
    st.stop()

total_distance = df_filt["distance_km"].sum()
total_time_h = df_filt["moving_time_h"].sum()
total_elev = df_filt["elev_gain_m"].sum()
n_acts = len(df_filt)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total distance (km)", f"{total_distance:,.1f}")
col2.metric("Total time (h)", f"{total_time_h:,.1f}")
col3.metric("Total elevation (m)", f"{total_elev:,.0f}")
col4.metric("Number of activities", f"{n_acts}")


# --------- MAIN LAYOUT ---------
tab_overview, tab_trends, tab_pace, tab_table = st.tabs(
    ["Overview", "Trends", "Pace / Intensity", "Raw data"]
)


# === TAB 1: OVERVIEW ===
with tab_overview:
    st.subheader("Distance & time by sport")

    by_sport = (
        df_filt.groupby("sport", as_index=False)
        .agg(
            distance_km=("distance_km", "sum"),
            moving_time_h=("moving_time_h", "sum"),
            n_acts=("activity_id", "count"),
        )
        .sort_values("distance_km", ascending=False)
    )

    # Bar chart: distance by sport
    dist_chart = (
        alt.Chart(by_sport)
        .mark_bar()
        .encode(
            x=alt.X("distance_km:Q", title="Total distance (km)"),
            y=alt.Y("sport:N", sort="-x", title=None),
            tooltip=[
                alt.Tooltip("sport:N", title="Sport"),
                alt.Tooltip("distance_km:Q", title="Distance (km)", format=".1f"),
                alt.Tooltip("moving_time_h:Q", title="Time (h)", format=".1f"),
                alt.Tooltip("n_acts:Q", title="# Activities"),
            ],
        )
    )

    st.altair_chart(dist_chart, use_container_width=True)

    # Weekly training load
    st.markdown("### Weekly training load")

    weekly = (
        df_filt.groupby("week", as_index=False)
        .agg(
            distance_km=("distance_km", "sum"),
            moving_time_h=("moving_time_h", "sum"),
        )
        .sort_values("week")
    )

    metric = st.selectbox(
        "Metric",
        options=["distance_km", "moving_time_h"],
        format_func=lambda x: "Distance (km)" if x == "distance_km" else "Time (h)",
        index=0,
        key="weekly_metric",
    )

    weekly_chart = (
        alt.Chart(weekly)
        .mark_line(point=True)
        .encode(
            x=alt.X("week:T", title="Week"),
            y=alt.Y(f"{metric}:Q", title="Distance (km)" if metric == "distance_km" else "Time (h)"),
            tooltip=[
                alt.Tooltip("week:T", title="Week"),
                alt.Tooltip(f"{metric}:Q", title="Value", format=".1f"),
            ],
        )
    )

    st.altair_chart(weekly_chart, use_container_width=True)


# === TAB 2: TRENDS ===
with tab_trends:
    st.subheader("Monthly distance by sport")

    monthly = (
        df_filt.groupby(["month", "sport"], as_index=False)
        .agg(distance_km=("distance_km", "sum"), n_acts=("activity_id", "count"))
        .sort_values(["month", "sport"])
    )

    monthly_chart = (
        alt.Chart(monthly)
        .mark_line(point=True)
        .encode(
            x=alt.X("month:T", title="Month"),
            y=alt.Y("distance_km:Q", title="Distance (km)"),
            color="sport:N",
            tooltip=[
                alt.Tooltip("month:T", title="Month"),
                alt.Tooltip("sport:N", title="Sport"),
                alt.Tooltip("distance_km:Q", title="Distance (km)", format=".1f"),
                alt.Tooltip("n_acts:Q", title="# Activities"),
            ],
        )
    )

    st.altair_chart(monthly_chart, use_container_width=True)

    st.markdown("### Long-term progression (cumulative distance)")

    df_filt_sorted = df_filt.sort_values("start_date_local")
    df_filt_sorted["cum_distance_km"] = df_filt_sorted["distance_km"].cumsum()

    cum_chart = (
        alt.Chart(df_filt_sorted)
        .mark_line()
        .encode(
            x=alt.X("start_date_local:T", title="Date"),
            y=alt.Y("cum_distance_km:Q", title="Cumulative distance (km)"),
            tooltip=[
                alt.Tooltip("start_date_local:T", title="Date"),
                alt.Tooltip("cum_distance_km:Q", title="Cumulative distance (km)", format=".1f"),
            ],
        )
    )

    st.altair_chart(cum_chart, use_container_width=True)


# === TAB 3: PACE / INTENSITY ===
with tab_pace:
    st.subheader("Pace distribution (runs)")

    runs = df_filt[df_filt["sport"].str.contains("Run", na=False)]

    if runs.empty:
        st.info("No running activities in the current selection.")
    else:
        pace_chart = (
            alt.Chart(runs)
            .transform_filter(alt.datum.pace_min_per_km > 0)
            .mark_bar()
            .encode(
                x=alt.X("pace_min_per_km:Q", bin=alt.Bin(maxbins=30), title="Pace (min/km)"),
                y=alt.Y("count():Q", title="Count"),
                tooltip=[
                    alt.Tooltip("count():Q", title="# Activities"),
                ],
            )
        )
        st.altair_chart(pace_chart, use_container_width=True)

        st.markdown("### Pace vs. distance (runs)")

        scatter = (
            alt.Chart(runs)
            .transform_filter(alt.datum.pace_min_per_km > 0)
            .mark_circle()
            .encode(
                x=alt.X("distance_km:Q", title="Distance (km)"),
                y=alt.Y("pace_min_per_km:Q", title="Pace (min/km)"),
                tooltip=[
                    alt.Tooltip("name:N", title="Activity"),
                    alt.Tooltip("date:T", title="Date"),
                    alt.Tooltip("distance_km:Q", title="Distance (km)", format=".1f"),
                    alt.Tooltip("pace_min_per_km:Q", title="Pace (min/km)", format=".2f"),
                ],
            )
        )

        st.altair_chart(scatter, use_container_width=True)

    st.markdown("### Heart rate (if available)")

    hr = df_filt[df_filt["avg_hr"].notna()]

    if hr.empty:
        st.info("No heart-rate data available in the current selection.")
    else:
        hr_chart = (
            alt.Chart(hr)
            .mark_circle()
            .encode(
                x=alt.X("moving_time_h:Q", title="Time (h)"),
                y=alt.Y("avg_hr:Q", title="Average HR"),
                color="sport:N",
                tooltip=[
                    alt.Tooltip("name:N", title="Activity"),
                    alt.Tooltip("sport:N", title="Sport"),
                    alt.Tooltip("moving_time_h:Q", title="Time (h)", format=".2f"),
                    alt.Tooltip("avg_hr:Q", title="Avg HR", format=".0f"),
                ],
            )
        )

        st.altair_chart(hr_chart, use_container_width=True)


# === TAB 4: RAW DATA ===
with tab_table:
    st.subheader("Raw activity data")
    st.dataframe(
        df_filt[
            [
                "activity_id",
                "name",
                "sport",
                "date",
                "distance_km",
                "moving_time_h",
                "elev_gain_m",
                "pace_min_per_km",
                "avg_hr",
            ]
        ].sort_values("date", ascending=False),
        use_container_width=True,
        height=600,
    )
    st.caption("You can download this as CSV from the download button below.")

    csv = df_filt.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download filtered data as CSV",
        data=csv,
        file_name="strava_activities_filtered.csv",
        mime="text/csv",
    )
