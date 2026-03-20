import argparse
from datetime import date

import pandas as pd
import streamlit as st

from march_madness_bets import data
from march_madness_bets.optimizer import multi_kelly_binary

pd.set_option("display.max_columns", None)
pd.set_option("display.max_rows", None)


def _get_candidate_bets(
    merged_df: pd.DataFrame,
    bankroll: float,
    max_bet_frac: float,
    target_date: date | None,
) -> pd.DataFrame:
    """Filter merged data and return positive-kelly candidate bets."""
    merged_df = merged_df[merged_df["event_time"] > pd.Timestamp.now(tz="US/Pacific")]

    if target_date is not None:
        merged_df = merged_df[merged_df.event_time.dt.date == target_date]
    else:
        merged_df = merged_df[
            merged_df.event_time.dt.date == merged_df.event_time.dt.date.min()
        ]

    merged_df = data.compute_log_ev(merged_df, bankroll=bankroll, max_bet_frac=max_bet_frac)
    merged_df = merged_df[
        (merged_df["type"] == "ML") | (merged_df["spread_val"].abs() >= 3.5)
    ]
    return merged_df[merged_df["kelly"] > 0].copy()


def run(
    bankroll: float = 100,
    target_date: date | None = None,
    max_bet_frac: float = 1.0,
    include_alt_spreads: bool = True,
) -> pd.DataFrame:
    """
    Run the betting optimizer.

    Args:
        bankroll: Total bankroll
        target_date: Target date for bets
        max_bet_frac: Maximum bet fraction of bankroll to wager on any single bet
        include_alt_spreads: Whether to include alternative spreads

    Returns:
        DataFrame of recommended bets
    """
    merged_df = data.get_combined_data(include_alt_spreads=include_alt_spreads)
    rec_bets = _get_candidate_bets(merged_df, bankroll, max_bet_frac, target_date)

    rec_bets["optimal_wager"] = multi_kelly_binary(
        game_ids=rec_bets.game_id.values,
        odds=rec_bets.odds.values,
        probs=rec_bets.prob_silver.values,
        bankroll=bankroll,
        max_bet_frac=max_bet_frac,
    )

    return rec_bets[rec_bets["optimal_wager"] > 0]


def _run_streamlit():
    """Render the Streamlit UI: sidebar inputs, step-by-step pipeline, and results table."""
    st.set_page_config(page_title="March Madness Optimizer", layout="wide")
    st.title("March Madness Bet Optimizer")

    # ── Sidebar inputs ───────────────────────────────────────────────────────
    with st.sidebar:
        st.header("Parameters")
        bankroll = st.number_input(
            "Bankroll ($)", min_value=1.0, value=100.0, step=10.0
        )
        max_bet_frac = st.slider(
            "Max bet fraction",
            min_value=0.01,
            max_value=1.0,
            value=1.0,
            step=0.01,
            help="Maximum fraction of bankroll wagered on any single bet",
        )
        include_alt_spreads = st.checkbox("Include alt spreads", value=False)

        use_date_filter = st.checkbox("Filter by date", value=False)
        target_date = None
        if use_date_filter:
            target_date = st.date_input("Target date", value=date.today())

        run_btn = st.button("Run Optimizer", type="primary", use_container_width=True)

    if not run_btn:
        st.info("Configure parameters in the sidebar and click **Run Optimizer**.")
        return

    # ── Pipeline ─────────────────────────────────────────────────────────────
    warnings_container = st.container()

    # Step 1 – Bovada
    with st.status("Fetching Bovada odds…", expanded=False) as bovada_status:
        bovada_raw = data.get_bovada_odds(include_alt_spreads=include_alt_spreads)
        st.write("Parsing Bovada response…")
        bovada_df = data.parse_bovada_odds(bovada_raw, competition_id="23110")
        bovada_status.update(
            label=f"Bovada: {len(bovada_df)} odds loaded", state="complete"
        )

    # Step 2 – Pinnacle
    with st.status("Fetching Pinnacle odds…", expanded=False) as pin_status:
        matchups, odds_raw = data.get_pinnacle_odds()
        st.write("Parsing Pinnacle response…")
        pinnacle_df = data.parse_pinnacle_odds(matchups, odds_raw)
        pin_status.update(
            label=f"Pinnacle: {len(pinnacle_df)} odds loaded", state="complete"
        )

    # Step 3 – Silver Bulletin
    with st.status(
        "Loading Silver Bulletin predictions…", expanded=False
    ) as silver_status:
        silver_df, silver_filename = data.get_silver_predictions()
        silver_status.update(
            label=f"Silver Bulletin ({silver_filename}): {len(silver_df)} teams loaded",
            state="complete",
        )

    # Step 4 – Merge & filter
    with st.status("Merging data sources…", expanded=False) as merge_status:
        merged_df, unmapped_pinnacle, unmapped_silver = data.merge_sources(
            bovada_df, pinnacle_df, silver_df
        )

        if unmapped_pinnacle:
            with warnings_container:
                st.warning(
                    f"Bovada teams not found in Pinnacle: {', '.join(sorted(unmapped_pinnacle))}"
                )
        if unmapped_silver:
            with warnings_container:
                st.warning(
                    f"Bovada teams not found in Silver Bulletin: {', '.join(sorted(unmapped_silver))}"
                )

        rec_bets = _get_candidate_bets(merged_df, bankroll, max_bet_frac, target_date)

        merge_status.update(
            label=f"Merged: {len(rec_bets)} candidate bets across "
            f"{rec_bets['game_id'].nunique()} games",
            state="complete",
        )

    if rec_bets.empty:
        st.warning("No positive-EV bets found after filtering.")
        return

    # Step 5 – Optimizer
    st.subheader("Running simultaneous Kelly optimizer…")
    opt_progress = st.progress(0.0, text="Evaluating combinations…")

    rec_bets["optimal_wager"] = multi_kelly_binary(
        game_ids=rec_bets.game_id.values,
        odds=rec_bets.odds.values,
        probs=rec_bets.prob_silver.values,
        bankroll=bankroll,
        max_bet_frac=max_bet_frac,
        progress_callback=lambda frac: opt_progress.progress(frac),
    )

    opt_progress.empty()

    result = rec_bets[rec_bets["optimal_wager"] > 0].copy()
    result["potential_profit"] = result["optimal_wager"] * (result["odds"] - 1)

    # ── Results ───────────────────────────────────────────────────────────────
    st.success(f"Optimizer complete — {len(result)} recommended bet(s)")

    if result.empty:
        st.info("Optimizer found no bets worth placing at this bankroll.")
        return

    display_cols = [
        "event_name",
        "bet_name",
        "type",
        "odds",
        "prob_silver",
        "optimal_wager",
        "potential_profit",
    ]
    display = result[display_cols].copy()
    display["prob_silver"] = display["prob_silver"].map("{:.1%}".format)
    display["odds"] = display["odds"].map("{:.3f}".format)
    display["optimal_wager"] = display["optimal_wager"].map("${:.2f}".format)
    display["potential_profit"] = (result["potential_profit"] / bankroll).map(
        "{:.1%}".format
    )

    st.dataframe(display, use_container_width=True, hide_index=True)

    total_wagered = result["optimal_wager"].sum()
    st.metric(
        "Total wagered",
        f"${total_wagered:.2f}",
        f"{total_wagered / bankroll:.1%} of bankroll",
    )

    with st.expander("Full dataframe (all candidate bets)"):
        st.dataframe(rec_bets, use_container_width=True)


# ── Entry points ──────────────────────────────────────────────────────────────

try:
    from streamlit.runtime.scriptrunner import get_script_run_ctx as _get_ctx

    _IN_STREAMLIT = _get_ctx() is not None
except Exception:
    _IN_STREAMLIT = False

if _IN_STREAMLIT:
    _run_streamlit()
elif __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bankroll", type=float, default=100)
    parser.add_argument(
        "--date", type=date.fromisoformat, default=None, metavar="YYYY-MM-DD"
    )
    parser.add_argument("--max_bet_frac", type=float, default=1.0)
    parser.add_argument("--include_alt_spreads", type=bool, default=False)
    args = parser.parse_args()

    result = run(bankroll=args.bankroll, target_date=args.date)
    result["potential_profit"] = (
        result["optimal_wager"] * (result["odds"] - 1) / args.bankroll
    )
    result = result[
        [
            "event_name",
            "bet_name",
            "type",
            "odds",
            "prob_silver",
            "kelly",
            "optimal_wager",
            "potential_profit",
        ]
    ]
    print(result)
