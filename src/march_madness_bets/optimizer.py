import itertools

import numpy as np
import scipy.optimize
from tqdm import tqdm


def multi_kelly_binary(
    game_ids: np.ndarray,
    odds: np.ndarray,
    probs: np.ndarray,
    bankroll: float,
    max_bet_frac: float = 1.0,
) -> np.ndarray:
    """
    Get optimal wagers for a set of binary bets using Kelly criterion.

    Args:
        game_ids: Array of game IDs. Used to select one bet per game.
        odds: Array of decimal odds for each bet.
        prob: Array of probabilities for each bet.
        bankroll: Total bankroll
        max_bet_frac: Maximum bet fraction of bankroll to wager on any single bet.

    Returns:
        Array of optimal wagers for each bet.
    """
    n = len(odds)

    unique_games = list(dict.fromkeys(game_ids))
    choices_per_game = [
        [i for i, g in enumerate(game_ids) if g == gid] for gid in unique_games
    ]

    best_ev = np.log(bankroll)
    best_wagers = np.zeros(n)

    combos = list(itertools.product(*choices_per_game))
    for combo in tqdm(combos):
        sel = list(combo)
        m = len(sel)
        p = probs[sel]
        o = odds[sel]

        outcome_bits = (np.arange(1 << m)[:, None] >> np.arange(m)) & 1
        outcome_probs = np.prod(np.where(outcome_bits, p, 1 - p), axis=1)

        def neg_ev(w):
            wealth = bankroll + outcome_bits @ (w * o) - w.sum()
            return -np.dot(outcome_probs, np.log(np.clip(wealth, 1e-9, None)))

        kelly_fracs = np.clip(p - (1 - p) / (o - 1), 0, max_bet_frac)
        x0 = kelly_fracs * bankroll

        res = scipy.optimize.minimize(
            neg_ev,
            x0,
            method="SLSQP",
            bounds=[(0, max_bet_frac * bankroll)] * m,
            constraints={"type": "ineq", "fun": lambda w: bankroll - w.sum()},
        )

        if res.success and -res.fun > best_ev:
            best_ev = -res.fun
            best_wagers = np.zeros(n)
            best_wagers[sel] = res.x

    return best_wagers
