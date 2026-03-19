# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

This project uses `uv` for package management and a `.venv` virtualenv.

```bash
# Install dependencies
uv sync --extra dev

# Run the Streamlit app
uv run streamlit run src/march_madness_bets/main.py

# Run the optimizer verification script
uv run python scripts/verify_optimizer.py

# Regenerate spread-to-cover-win-diff lookup (scrapes teamrankings.com)
uv run python src/march_madness_bets/spread_cover_rate.py

# Launch Jupyter for notebooks
uv run jupyter notebook
```

There are no automated tests — `scripts/verify_optimizer.py` is the manual integration test for `SimultaneousKellyOptimizer`.

## Architecture

The project finds +EV betting opportunities for March Madness by combining odds from two bookmakers with win probability estimates from a prediction model.

**Data pipeline (`src/march_madness_bets/data.py`)**

`get_combined_data()` is the main entry point:
1. Pulls live Bovada odds (REST, no auth needed) and filters to `competitionId="23110"` (NCAA Tournament).
2. Pulls live Pinnacle odds via their guest API (`league 493`). Parses spreads and moneylines; vig-removes implied probabilities.
3. Loads Silver Bulletin prediction CSVs from `src/march_madness_bets/predictions/gamepreds*.csv` (latest file by name sort). These give per-team ML win probabilities.
4. Merges on `(team, type, spread_val)`. For spread bets, Silver prob is estimated as `prob_silver_ML + (prob_pinnacle_spread - prob_pinnacle_ML)`.
5. Computes Kelly fraction per bet.

Team name mismatches between sources are resolved by JSON maps in `src/march_madness_bets/maps/`:
- `team_names_pinnacle_to_bovada.json` — Pinnacle → Bovada names
- `team_names_silver_to_bovada.json` — Silver Bulletin → Bovada names

**Optimizer (`src/march_madness_bets/optimizer.py`)**

`SimultaneousKellyOptimizer.optimize()` finds the globally optimal set of bets using simultaneous Kelly criterion:
- Constraint: at most one bet per game (iterates all `product(*choices_per_game)` combinations).
- For each combination, uses SLSQP (via `scipy.optimize.minimize`) to maximize `E[log(wealth)]` over all `2^n` game outcomes.
- Returns the combination+wager set with the highest expected log-wealth.

**Spread cover rate (`src/march_madness_bets/spread_cover_rate.py`)**

Precomputes a lookup table (`maps/spread_to_cover_win_diff.json`) mapping each spread value to the difference between historical ATS cover rate and outright win rate. Uses Bayesian smoothing and a fitted logistic function. This adjusts ML probabilities to estimate spread cover probabilities.

**Notebooks (`notebooks/`)**

- `March_Madness_2026_odds_compare.ipynb` — main analysis notebook; pulls live data and runs optimizer.
- `pinnacle.ipynb` — Pinnacle-specific data exploration.
- `simultaneous_ml_torch.ipynb` — experimental PyTorch-based optimizer approach.

**Samples (`samples/`)**

`bovada_odds.json` — cached Bovada API response for offline development.
