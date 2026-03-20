import json
from pathlib import Path

import numpy as np
import pandas as pd
import requests


def get_bovada_odds(include_alt_spreads: bool = False):
    odds_url = "https://www.bovada.lv/services/sports/event/coupon/events/A/description/basketball/college-basketball"
    params = {
        "preMatchOnly": "true",
        "lang": "en",
    }
    if not include_alt_spreads:
        params["marketFilterId"] = "def"
    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    }
    print("Pulling Bovada odds...")
    odds_raw = requests.get(odds_url, params=params, headers=headers).json()

    return odds_raw


def get_pinnacle_odds() -> pd.DataFrame:
    BASE_URL = "https://guest.api.arcadia.pinnacle.com/0.1/leagues/493"
    matchups_response = requests.get(f"{BASE_URL}/matchups")
    matchups_response.raise_for_status()

    print("Pulling Pinnacle odds...")
    odds_response = requests.get(f"{BASE_URL}/markets/straight")
    odds_response.raise_for_status()

    matchups = matchups_response.json()
    odds = odds_response.json()

    return matchups, odds


def american_to_decimal(american_odds: int) -> float:
    """Convert American odds to decimal odds."""
    if american_odds > 0:
        return (american_odds / 100.0) + 1.0
    else:
        return (100.0 / abs(american_odds)) + 1.0


def parse_pinnacle_odds(matchups: list, odds: list) -> pd.DataFrame:
    """
    Parse the raw matchups and odds data from Pinnacle and return a pandas DataFrame.

    Args:
        matchups: Raw matchups list from /matchups endpoint.
        odds: Raw odds list from /markets/straight endpoint.

    Returns:
        pd.DataFrame with columns: event_name, team, bet_name, type, spread_val,
                                    odds, decimal_odds, implied_prob_vig_adjusted,
                                    alignment, matchup_id, key, max_risk_stake
    """
    # Build lookup: matchup_id -> {home: name, away: name}
    matchup_info = {}
    for m in matchups:
        if m.get("type") != "matchup":
            continue
        mid = m["id"]
        teams = {}
        for p in m.get("participants", []):
            alignment = p.get("alignment")
            if alignment in ("home", "away"):
                teams[alignment] = p["name"]
        if teams:
            matchup_info[mid] = {
                "teams": teams,
                "start_time": m.get("startTime"),
            }

    rows = []
    for o in odds:
        mid = o.get("matchupId")
        if mid not in matchup_info:
            continue

        # Only full-game markets (period 0)
        if o.get("period") != 0:
            continue

        market_type = o.get("type")
        if market_type not in ("moneyline", "spread"):
            continue

        is_alternate = o.get("isAlternate", False)
        info = matchup_info[mid]
        teams = info["teams"]
        event_name = f"{teams.get('away', '?')} @ {teams.get('home', '?')}"
        max_risk = None
        for lim in o.get("limits", []):
            if lim.get("type") == "maxRiskStake":
                max_risk = lim["amount"]

        # Calculate total implied probability for vig adjustment
        prices = o.get("prices", [])
        decoded_prices = []
        total_implied_prob = 0
        for price_entry in prices:
            american_odds = price_entry.get("price")
            decimal_odds = american_to_decimal(american_odds)
            implied_prob = 1.0 / decimal_odds
            total_implied_prob += implied_prob
            decoded_prices.append(
                {
                    "price_entry": price_entry,
                    "decimal_odds": decimal_odds,
                    "implied_prob": implied_prob,
                }
            )

        for item in decoded_prices:
            price_entry = item["price_entry"]
            decimal_odds = item["decimal_odds"]
            implied_prob = item["implied_prob"]

            # Vig adjusted probability
            vig_adj_prob = (
                implied_prob / total_implied_prob if total_implied_prob > 0 else 0
            )

            designation = price_entry.get("designation")
            team_name = teams.get(designation, designation)
            american_odds = price_entry.get("price")
            spread_val = price_entry.get("points", 0)

            if market_type == "moneyline":
                bet_type = "ML"
                spread_val = 0
            elif is_alternate:
                bet_type = "Alt Spread"
            else:
                bet_type = "Spread"

            rows.append(
                {
                    "event_name": event_name,
                    "team": team_name,
                    "type": bet_type,
                    "spread_val": spread_val,
                    "american_odds_pinnacle": american_odds,
                    "odds": decimal_odds,
                    "prob_pinnacle": vig_adj_prob,
                    "max_stake_pinnacle": max_risk,
                }
            )

    pinnacle_df = pd.DataFrame(rows)

    with open(
        Path(__file__).parent / "maps" / "team_names_pinnacle_to_bovada.json", "r"
    ) as f:
        map_pinnacle_to_bovada = json.load(f)
    pinnacle_df["team"] = pinnacle_df["team"].replace(map_pinnacle_to_bovada)

    return pinnacle_df


def get_bovada_max_bet(outcome_id: str, price_id: str) -> int:
    # TODO: Requires login cookies
    raise NotImplementedError
    # url = "https://services.bovada.lv/services/sports/bet/betslip/maxStake"
    # headers = {
    #     "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    # }

    # payload = {
    #     "device": "DESKTOP",
    #     "channel": "WEB_BS",
    #     "selections": {
    #         "selection": [
    #             {
    #                 "outcomeId": str(outcome_id),
    #                 "id": 0,
    #                 "system": "A",
    #                 "priceId": str(price_id),
    #                 "oddsFormat": "AMERICAN",
    #             }
    #         ]
    #     },
    #     "groups": {
    #         "group": [
    #             {
    #                 "id": 0,
    #                 "type": "STRAIGHT",
    #                 "groupSelections": [
    #                     {
    #                         "groupSelection": [
    #                             {"selectionId": 0, "order": 0, "isBanker": False}
    #                         ]
    #                     }
    #                 ],
    #             }
    #         ]
    #     },
    #     "bets": {
    #         "bet": [
    #             {
    #                 "betGroups": {"groupId": [0]},
    #                 "betType": "SINGLE",
    #                 "isBox": False,
    #                 "oddsFormat": "AMERICAN",
    #                 "specifyingRisk": True,
    #                 "stakePerLine": 0,
    #                 "potentialWin": 0,
    #             }
    #         ]
    #     },
    # }

    # try:
    #     response = requests.post(url, headers=headers, json=payload, timeout=12)
    #     if response.status_code != 200:
    #         print(
    #             f"[{outcome_id}] HTTP {response.status_code}: {response.text}",
    #             flush=True,
    #         )
    #         return 0
    #     return response.json().get("maxStake", 0)
    # except Exception as e:
    #     print(f"[{outcome_id}] Exception: {e}", flush=True)
    #     return 0


def parse_bovada(row):
    """
    Helper method to parse a single row of the Bovada DataFrame.
    """
    team_name = row["description"].split("(")[0].strip()
    if pd.isnull(row["price.handicap"]):
        bet_type = "ML"
        spread_val = 0
        bet_name = f"{team_name} ML"
    else:
        bet_type = "Spread" if row["spread_type"] == "standard" else "Alt Spread"
        spread_val = float(row["price.handicap"])
        bet_name = f"{team_name} {spread_val:+.1f}"
    return pd.Series(
        {
            "event_time": row["start_datetime"].tz_convert("US/Pacific"),
            "event_name": row["event_name"],
            "team": row["description"].split("(")[0].strip(),
            "bet_name": bet_name,
            "type": bet_type,
            "spread_val": spread_val,
            "odds": float(row["price.decimal"]),
            "outcome_id": row["id"],
            "price_id": row["price.id"],
        }
    )


def parse_bovada_odds(
    odds_raw: dict, competition_id: str = None, get_max_bets: bool = False
) -> pd.DataFrame:
    """
    Parse the raw odds data from Bovada and return a pandas DataFrame.
    Filters for a specific competition ID.

    Args:
        odds_raw: Raw odds data from get_odds().
        competition_id: Competition ID to filter for.
        get_max_bets: Whether to get the max bet for each outcome.

    Returns:
        pd.DataFrame: DataFrame with parsed odds data.
    """
    bovada_df = []
    for event in odds_raw[0]["events"]:
        start_time_epoch = int(event["startTime"])
        start_datetime = pd.to_datetime(start_time_epoch, unit="ms", utc=True)
        event_id = event["id"]
        event_name = event["description"]
        if event.get("competitionId") != competition_id:
            continue

        for group in event["displayGroups"]:
            group_desc = group["description"]
            if group_desc == "Game Lines":
                spread_type = "standard"
            elif group_desc == "Alternate Lines":
                spread_type = "alternate"
            else:
                continue
            for market in group["markets"]:
                if market["period"]["description"] == "Game":
                    if (
                        (market["description"] == "Moneyline")
                        or (market["description"] == "Point Spread")
                        or (market["description"] == "Spread")
                    ):
                        df = pd.json_normalize(market["outcomes"])
                        df["start_datetime"] = start_datetime
                        df["event_id"] = event_id
                        df["event_name"] = event_name
                        df["spread_type"] = spread_type
                        bovada_df.append(df)
    bovada_df = pd.concat(bovada_df).reset_index().sort_values("start_datetime")

    bovada_df = bovada_df.apply(parse_bovada, axis=1)

    if get_max_bets:
        bovada_df["max_bet"] = bovada_df.apply(
            lambda x: get_bovada_max_bet(x["outcome_id"], x["price_id"]), axis=1
        )

    return bovada_df


def get_silver_predictions():
    """
    Get the latest Silver Bulliten predictions.

    Returns:
        pd.DataFrame: DataFrame with silver predictions.
    """
    predictions_path = Path(__file__).parent / "predictions"

    latest_preds = sorted([*predictions_path.glob("gamepreds*.csv")])[-1]

    print(f"Using predictions file: {latest_preds.name}")

    df = pd.read_csv(latest_preds)
    df = pd.concat(
        [
            df[["full_sb_name_a", "team_a_odds"]].rename(
                columns={"full_sb_name_a": "team", "team_a_odds": "prob_silver"}
            ),
            df[["full_sb_name_b", "team_b_odds"]].rename(
                columns={"full_sb_name_b": "team", "team_b_odds": "prob_silver"}
            ),
        ],
    ).sort_index()

    df["type"] = "ML"
    df["spread_val"] = 0.0

    with open(
        Path(__file__).parent / "maps" / "team_names_silver_to_bovada.json", "r"
    ) as f:
        map_silver_to_bovada = json.load(f)
    df["team"] = df["team"].replace(map_silver_to_bovada)

    return df


def merge_sources(
    bovada_df: pd.DataFrame,
    pinnacle_df: pd.DataFrame,
    silver_df: pd.DataFrame,
) -> tuple[pd.DataFrame, set, set]:
    """
    Merge pre-fetched Bovada, Pinnacle, and Silver Bulletin DataFrames.
    Computes vig-adjusted spread probabilities and Kelly fractions.

    Returns:
        (merged_df, unmapped_pinnacle, unmapped_silver)
    """
    unmapped_pinnacle = set(bovada_df.team) - set(pinnacle_df.team)
    unmapped_silver = set(bovada_df.team) - set(silver_df.team)

    merged = bovada_df.merge(
        pinnacle_df,
        on=["team", "type", "spread_val"],
        suffixes=["", "_pinnacle"],
        how="inner",
    )
    merged = merged.merge(silver_df, on=["team", "type", "spread_val"], how="left")

    merged = merged[
        [
            "event_time",
            "event_name",
            "team",
            "bet_name",
            "type",
            "spread_val",
            "odds",
            "prob_pinnacle",
            "prob_silver",
        ]
    ]

    # For spread rows: prob_silver = prob_silver_ML + (prob_pinnacle_spread - prob_pinnacle_ML)
    ml_rows = merged[merged["type"] == "ML"][
        ["event_name", "team", "prob_pinnacle", "prob_silver"]
    ]
    ml_lookup = ml_rows.drop_duplicates(subset=["event_name", "team"]).set_index(
        ["event_name", "team"]
    )
    spread_mask = merged["type"].isin(["Spread", "Alt Spread"])
    keys = merged.loc[spread_mask, ["event_name", "team"]].apply(tuple, axis=1)
    ml_pinnacle = keys.map(ml_lookup["prob_pinnacle"]).values
    ml_silver = keys.map(ml_lookup["prob_silver"]).values
    merged.loc[spread_mask, "prob_silver"] = ml_silver + (
        merged.loc[spread_mask, "prob_pinnacle"].values - ml_pinnacle
    )

    merged["kelly"] = merged["prob_silver"] - (
        (1 - merged["prob_silver"]) / (merged["odds"] - 1)
    )
    merged["game_id"] = pd.factorize(merged["event_name"])[0]

    return merged, unmapped_pinnacle, unmapped_silver


def get_combined_data(include_alt_spreads=True):
    """
    Fetch and merge data from Bovada, Pinnacle, and Silver Bulletin.

    Returns:
        pd.DataFrame: DataFrame with combined data.
    """
    bovada_df = parse_bovada_odds(
        get_bovada_odds(include_alt_spreads), competition_id="23110"
    )
    pinnacle_df = parse_pinnacle_odds(*get_pinnacle_odds())
    silver_df = get_silver_predictions()

    merged, unmapped_pinnacle, unmapped_silver = merge_sources(
        bovada_df, pinnacle_df, silver_df
    )

    if unmapped_pinnacle:
        print(f"WARNING - Bovada names not found in Pinnacle data: {unmapped_pinnacle}")
    if unmapped_silver:
        print(f"WARNING - Bovada names not found in Silver data: {unmapped_silver}")

    return merged


def compute_log_ev(df: pd.DataFrame, bankroll=10000, max_bet_frac=0.2):
    """
    Compute the log expected value for each bet in the DataFrame.

    Args:
        df: combined dataframe from get_combined_data()
        bankroll: Total bankroll
        max_bet_frac: Maximum fraction of bankroll to bet on any single bet.

    Returns:
        pd.DataFrame: DataFrame with added 'log_ev' column.
    """
    prob = df["prob_silver"]
    kelly_clamped = np.minimum(df["kelly"], max_bet_frac)
    wager_amt = np.maximum(0, kelly_clamped) * bankroll
    net_odds = df["odds"] - 1
    not_prob = 1 - prob

    df["log_ev"] = prob * np.log(bankroll + wager_amt * net_odds) + not_prob * np.log(
        bankroll - wager_amt
    )
    return df
