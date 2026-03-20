# March Madness Bet Sizer

## Overview

This tool finds +EV (positive expected value) betting opportunities for March Madness by combining odds from two bookmakers with win probability estimates from a prediction model.

It pulls live odds from **Bovada** and **Pinnacle**, loads win probability predictions from **Silver Bulletin** CSVs, and uses the **simultaneous Kelly criterion** to compute the globally optimal set of bets and wager sizes across all games.

### How it works

1. **Odds ingestion** — Live moneyline and spread odds are pulled from Bovada and Pinnacle. Pinnacle's vig-removed implied probabilities serve as the market baseline.
2. **Prediction model** — Silver Bulletin ML win probabilities are loaded from `src/march_madness_bets/predictions/gamepreds*.csv` (latest file used automatically).
3. **Edge calculation** — Kelly fraction is computed for each bet where the model probability exceeds the market-implied probability.
4. **Portfolio optimization** — `multi_kelly_binary` finds the optimal combination of bets (at most one per game) and wager sizes by maximizing expected log-wealth using SLSQP.

## Running the Streamlit App

```bash
# Install dependencies
uv sync --extra dev

# Launch the app
uv run streamlit run src/march_madness_bets/main.py
```

The app displays current +EV bets, Kelly-optimal wager sizes, and expected profit.

## Other Commands

```bash
# Regenerate the spread-cover-rate lookup table (scrapes teamrankings.com)
uv run python src/march_madness_bets/spread_cover_rate.py

# Launch Jupyter for notebooks
uv run jupyter notebook
```

## Project Structure

```
src/march_madness_bets/
  main.py                  # Streamlit app entry point
  data.py                  # Data pipeline (odds + predictions merge)
  optimizer.py             # multi_kelly_binary optimizer function
  spread_cover_rate.py     # Spread-to-cover-rate lookup generation
  predictions/             # Silver Bulletin CSV files
  maps/                    # Team name mapping JSONs and spread lookup table

notebooks/
  March_Madness_2026_odds_compare.ipynb   # Main analysis notebook
  pinnacle.ipynb                          # Pinnacle data exploration
  simultaneous_ml_torch.ipynb             # Experimental PyTorch optimizer

samples/
  bovada_odds.json         # Cached Bovada response for offline dev
```

## Team Name Mappings

Odds sources use different team names. JSON maps in `src/march_madness_bets/maps/` resolve mismatches:
- `team_names_pinnacle_to_bovada.json` — Pinnacle → Bovada
- `team_names_silver_to_bovada.json` — Silver Bulletin → Bovada
