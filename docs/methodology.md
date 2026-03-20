# Methodology

This document describes each step the optimizer takes from raw data to recommended bets.

---

## 1. Pull Bovada odds

Bovada is the book we are betting into. We pull live moneyline and point spread odds for all NCAA Tournament games, including alternate spread lines if enabled.

---

## 2. Pull Pinnacle odds

Pinnacle is a market-making book, meaning they offer low-vig lines that sit very close to the true probability of an event. Other books like Bovada charge higher vig, which skews their implied probabilities away from reality. We use Pinnacle's odds not to bet into, but as a clean probability estimate for each outcome.

**Vig removal**: Bookmakers pad their odds so that the implied probabilities of both sides sum to more than 100%. To recover unbiased probabilities, we divide each side's implied probability by the total, normalizing them to sum to exactly 1.

---

## 3. Load Silver Bulletin predictions

Silver Bulletin publishes a CSV of moneyline win probabilities for each tournament game, derived from their prediction model. We load the most recent file and treat these probabilities as our model's estimate of each team's true chance of winning.

---

## 4. Combine the sources

We combine Bovada, Pinnacle, and Silver Bulletin into a single dataset. Only bets that appear on both Bovada and Pinnacle are kept — if a line isn't available on both, we can't compute everything we need.

**Estimating spread probabilities**: Silver Bulletin only publishes outright win probabilities, not spread cover probabilities. To estimate the probability that a team covers a given spread, we use the following logic: take Pinnacle's spread probability, then shift it by however much Silver disagrees with Pinnacle on the moneyline.

$$P_{\text{Silver, spread}} = P_{\text{Silver, ML}} + (P_{\text{Pinnacle, spread}} - P_{\text{Pinnacle, ML}})$$

This assumes Silver's edge over the market is consistent between the moneyline and spread markets.

---

## 5. Identify +EV bets

For each bet, we compute the Kelly fraction — a measure of how much edge we have:

$$f = p - \frac{1 - p}{b}$$

where $p$ is Silver's probability and $b$ is the net decimal odds (i.e. profit per $1 wagered). A positive Kelly fraction means the bet is +EV: our model thinks the true probability is higher than what Bovada is implying.

Only bets with a positive Kelly fraction are considered. Spread bets on very tight lines (under 3.5 points) are excluded to reduce noise.

---

## 6. Optimize the portfolio

Computing Kelly fractions independently for each bet ignores two important constraints: we can only bet one side per game, and outcomes across bets are not independent (each game has one result that resolves all bets on it simultaneously).

The optimizer finds the globally optimal set of bets and wager sizes by:

1. Enumerating every possible combination of one bet per game (including passing on a game entirely).
2. For each combination, finding the wager amounts that maximize expected log-wealth across all possible outcomes:

$$\max_{\mathbf{w}} \sum_{\text{outcomes}} P(\text{outcome}) \cdot \log\!\left(\text{bankroll} + \text{net PnL}(\text{outcome}, \mathbf{w})\right)$$

3. Selecting the combination and wager sizes that produce the highest expected log-wealth.

Maximizing expected log-wealth is the Kelly criterion generalized to a portfolio — it produces the wager sizes that maximize long-run bankroll growth.

---

## 7. Spread cover rate lookup (alternate approach, not currently used)

An alternative way to estimate spread cover probabilities is via a precomputed lookup table mapping each spread value to the historical difference between ATS cover rate and outright win rate, using NCAA game data since 2003. Rather than borrowing the spread adjustment from Pinnacle's lines (as in step 4), this would derive the adjustment purely from historical data.

Both rates are smoothed using Bayesian shrinkage — spread values with few historical games are pulled toward a prior (50% for cover rate; a fitted logistic curve for win rate) to avoid overfitting sparse data.
