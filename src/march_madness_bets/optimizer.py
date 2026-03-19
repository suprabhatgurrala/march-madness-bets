"""Simultaneous Kelly optimizer with group selection constraints.

Since bets on different games are independent and we select at most one bet
per game, the expected log growth decomposes as a sum:

    E[ln(W/W0)] = sum_i [ p_i * ln(1 + f_i*(d_i-1)) + (1-p_i) * ln(1 - f_i) ]

We enumerate all valid group selections (one bet per game) and for each
selection, solve a fast convex optimization over the continuous fractions.
"""

import numpy as np
import pandas as pd


def _optimize_fractions(probs, net_odds, max_f, min_profit_frac=0.03):
    """Find optimal Kelly fractions for a fixed selection of independent bets.

    Uses the analytical Kelly formula and applies the minimum profit constraint.
    """
    n = len(probs)
    if n == 0:
        return np.array([]), 0.0

    # Kelly formula: f = p - (1-p)/b
    fracs = probs - (1.0 - probs) / net_odds
    fracs = np.clip(fracs, 0, max_f)

    # Apply 3% potential profit constraint: fraction * net_odds >= threshold
    # Potential profit is relative to total bankroll.
    fracs[fracs * net_odds < min_profit_frac] = 0.0

    # Calculate log growth contribution
    # E[ln(W/W0)] = p*ln(1 + f*b) + (1-p)*ln(1-f)
    growth_contributions = probs * np.log1p(fracs * net_odds) + (
        1.0 - probs
    ) * np.log1p(-fracs)

    return fracs, growth_contributions


def optimize_kelly(
    df: pd.DataFrame,
    bankroll: float,
    max_bet_frac: float = 0.20,
    min_profit_frac: float = 0.03,
    prob_col: str = "prob_silver",
    odds_col: str = "odds",
    group_col: str = "event_name",
) -> pd.DataFrame:
    """Simultaneous Kelly optimizer with at-most-one-bet-per-group constraint.

    Independently optimizes each candidate bet and selects the best one per group.
    This assumes an additive log-growth model (appropriate for independent games).

    Args:
        df: DataFrame of candidate bets.
        bankroll: Total bankroll in dollars.
        max_bet_frac: Max fraction of bankroll on any single bet.
        min_profit_frac: Minimum potential profit (as fraction of bankroll) to wager.
        prob_col: Column with win probability.
        odds_col: Column with decimal odds.
        group_col: Column for grouping bets by game/event.

    Returns:
        DataFrame of selected bets with optimal fractions and dollar amounts.
    """
    if df.empty:
        return pd.DataFrame()

    work = df.copy()
    probs = work[prob_col].values
    net_odds = work[odds_col].values - 1.0

    # Calculate optimal fractions and growth contributions for EVERY bet independently
    fracs, growths = _optimize_fractions(probs, net_odds, max_bet_frac, min_profit_frac)

    work["fraction"] = fracs
    work["growth_rate"] = growths
    work["bet_amount"] = (fracs * bankroll).round(2)
    work["potential_profit_pct"] = (fracs * net_odds).round(4)

    # For each group, pick the bet with the highest growth_rate
    # If the highest growth_rate is 0 (no profitable bet meeting threshold), skip.
    best_per_group = (
        work[work["growth_rate"] > 0]
        .sort_values("growth_rate", ascending=False)
        .drop_duplicates(group_col)
    )

    return best_per_group.sort_index()
