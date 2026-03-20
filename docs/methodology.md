# Methodology

This document describes each step the optimizer takes from raw data to recommended bets.

---

## 1. Fetch Bovada odds

`data.get_bovada_odds()` hits Bovada's college basketball REST endpoint (no auth required). The response is filtered to `competitionId="23110"` (NCAA Tournament). For each game, moneyline and point spread markets from the "Game Lines" and "Alternate Lines" display groups are extracted. Each outcome is normalized into a row with:

- `team`, `type` (ML / Spread / Alt Spread), `spread_val`, `odds` (decimal), `event_time`

Alt spreads are included or excluded based on the `include_alt_spreads` flag.

---

## 2. Fetch Pinnacle odds

`data.get_pinnacle_odds()` calls Pinnacle's guest API for NCAA league 493, pulling `/matchups` (team names) and `/markets/straight` (prices).

`data.parse_pinnacle_odds()` processes the response:

- Only full-game markets (period 0) and moneyline/spread types are kept.
- **Vig removal**: for each market, each side's implied probability (`1 / decimal_odds`) is divided by the total implied probability across both sides, yielding a vig-free probability `prob_pinnacle`.
- Team names are remapped via `maps/team_names_pinnacle_to_bovada.json` to match Bovada naming.

---

## 3. Load Silver Bulletin predictions

`data.get_silver_predictions()` reads the latest `gamepreds*.csv` from `src/march_madness_bets/predictions/` (sorted lexicographically, last file wins). Each row contains two teams and their win probabilities (`team_a_odds`, `team_b_odds`). The file is unpivoted into one row per team with `type="ML"` and `spread_val=0`.

Team names are remapped via `maps/team_names_silver_to_bovada.json`.

---

## 4. Merge sources

`data.merge_sources()` joins all three sources:

1. **Bovada ⋈ Pinnacle** on `(team, type, spread_val)` — inner join, so only bets available on both books are kept.
2. **⋈ Silver** on `(team, type, spread_val)` — left join; Silver only provides ML rows directly.

**Spread probability estimation**: Silver Bulletin only publishes moneyline win probabilities. For spread bets, the model probability is estimated as:

```
prob_silver_spread = prob_silver_ML + (prob_pinnacle_spread - prob_pinnacle_ML)
```

This assumes that the Silver model's edge over the market is the same shape across the moneyline and spread markets — i.e. it shifts the market-implied spread probability by however much Silver disagrees with the market on the moneyline.

Any Bovada teams not found in Pinnacle or Silver are logged as warnings.

---

## 5. Compute Kelly fractions

For each bet, the standard Kelly fraction is computed:

```
kelly = prob_silver - (1 - prob_silver) / (odds - 1)
```

A positive Kelly indicates a +EV bet (model probability exceeds the breakeven probability implied by the odds).

---

## 6. Filter candidate bets

Before running the optimizer, bets are filtered down to a candidate set:

- Only upcoming games (event time > now) on the target date (defaults to the earliest game date available).
- Spread bets with `|spread_val| < 3.5` are excluded to avoid noise on very tight lines.
- Only bets with `kelly > 0` are kept.

---

## 7. Simultaneous Kelly optimization

`optimizer.multi_kelly_binary()` finds the globally optimal portfolio of bets.

**The problem**: Kelly fractions computed independently per bet assume the bets are independent. In reality, we can only bet one side per game, and the outcomes are correlated through game results. The optimizer accounts for this.

**Algorithm**:

1. Group candidate bets by `game_id`. For each game, enumerate all possible choices (each bet on that game, including "no bet" implicitly via zero wager).
2. Use `itertools.product` to enumerate every combination of one bet per game — e.g. 3 games with 2 candidates each yields 8 combinations.
3. For each combination of `m` selected bets:
   - Enumerate all `2^m` possible outcomes (win/loss for each bet).
   - Compute the probability of each outcome as the product of per-bet win/loss probabilities.
   - Use SLSQP (`scipy.optimize.minimize`) to maximize expected log-wealth:
     ```
     E[log(wealth)] = sum over outcomes: P(outcome) * log(bankroll + net_pnl(outcome))
     ```
   - Wager bounds: `[0, max_bet_frac * bankroll]` per bet; total wagers ≤ bankroll.
   - Warm-start: initialize from single-bet Kelly fracs × bankroll.
4. Keep the combination+wager set with the highest `E[log(wealth)]`.

Bets with an optimal wager of zero are excluded from the final output.

---

## 8. Spread cover rate lookup (offline preprocessing)

`spread_cover_rate.py` generates `maps/spread_to_cover_win_diff.json`, which maps each spread value to `cover_rate - win_rate`. This is used to adjust moneyline probabilities for spread bets independently of the Pinnacle market adjustment described in step 4.

Steps:
1. Scrape historical NCAA ATS results since 2003 from teamrankings.com.
2. Fit a logistic function to the raw win rate by spread using weighted least squares (weights = game count).
3. Apply Bayesian smoothing to both cover rate and win rate, regressing toward priors (0.5 for cover rate, logistic fit for win rate) when sample sizes are small (`m=2000`).
4. Store `cover_rate - win_rate` per spread value as the lookup table.
