from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

SPREAD_LOOKUP_PATH = Path(__file__).parent / "maps" / "spread_to_cover_win_diff.json"


def get_spread_to_cover_win_diff():
    if SPREAD_LOOKUP_PATH.exists():
        spread_to_cover_win_diff = pd.read_json(SPREAD_LOOKUP_PATH, orient="index")[0]
        spread_to_cover_win_diff.index = spread_to_cover_win_diff.index.astype(float)
        return spread_to_cover_win_diff
    else:
        main()
        return get_spread_to_cover_win_diff()


def get_results_by_spread():
    """
    Pulls NCAA Basketball game results by spread.
    """
    url = "https://www.teamrankings.com/ncb/odds-history/results/?season-filter=since_2003"
    try:
        tables = pd.read_html(url)
        if not tables:
            print(f"Error: No tables found at {url}")
            return None

        df = tables[0]

        # Validate table structure before processing
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(0)
        else:
            print("Warning: Table header structure unexpected, skipping droplevel")

        df["Cover Rate"] = df["Cover %"].str.replace("%", "").astype(float) / 100
        df["Raw Win Rate"] = df["Win %"].str.replace("%", "").astype(float) / 100
        return df

    except pd.errors.EmptyDataError:
        print(f"Error: No data found at {url}")
    except ValueError as e:
        print(f"Error: Could not parse HTML from {url}: {e}")
    except Exception as e:
        print(f"Error: Unexpected failure fetching data from {url}: {e}")

    return None


def compute_bayesian(v, R, C, m=5000) -> pd.Series:
    """
    Computes the Bayesian adjusted value.
    Put simply, we trust results that occur more frequently
    and regress less common results to the underlying assumption.

    Args:
        v: Number of games
        R: raw value
        C: baseline value
        m: threshold for v, when v is smaller than m, we trust the baseline value more

    Returns:
        pd.Series: Bayesian adjusted values
    """
    return (v * R + m * C) / (v + m)


def win_prob_function(x, k):
    """
    Computes the win probability for a given spread using a logistic function.

    Args:
        x: The spread
        k: The steepness of the curve

    Returns:
        The win probability for the given spread
    """
    return 1 / (1 + np.exp(x * k))


def optimize_k(historical_ats_df):
    """
    Optimizes the k parameter for the win probability function.

    Args:
        historical_ats_df: DataFrame containing historical ATS data

    Returns:
        The optimized k parameter
    """
    x_data = historical_ats_df["Closing Spread"].astype(int).values
    y_data = historical_ats_df["Raw Win Rate"].astype(float).values
    weights = historical_ats_df["Game Count"].astype(int).values

    popt, pcov = curve_fit(win_prob_function, x_data, y_data, p0=[1], sigma=1 / weights)
    best_k = popt[0]
    print(f"Optimal constant (k): {best_k:.4f}")
    return best_k


def plot_win_prob_function(historical_ats_df, k):
    """
    Plots the win probability function for a given k parameter.

    Args:
        historical_ats_df: DataFrame containing historical ATS data
        k: The k parameter for the win probability function
    """
    Path("plots").mkdir(parents=True, exist_ok=True)
    x_data = historical_ats_df["Closing Spread"].astype(int).values
    y_data = historical_ats_df["Raw Win Rate"].astype(float).values

    plt.figure(figsize=(16, 9))
    plt.scatter(x_data, y_data)
    plt.plot(x_data, win_prob_function(x_data, k), label=f"k={k:.4f}", color="C1")
    plt.legend()
    plt.title("Win Probability Function")
    plt.xlabel("Closing Spread")
    plt.ylabel("Win Probability")
    plt.savefig("plots/win_prob_function.png", dpi=300, bbox_inches="tight")
    plt.close()


def main():
    """
    Main method which creates the lookup of spread to win probability adjustment.
    Using your model's moneyline probabilities, you can compute the cover rate for any spread using this lookup.
    """
    historical_ats_df = get_results_by_spread()
    k = optimize_k(historical_ats_df)
    plot_win_prob_function(historical_ats_df, k)

    # Lower values of m value raw data more, while higher values trust the baseline more
    m = 2000

    # Get the Bayesian adjusted cover rate for each spread value
    # Using 0.5 as the baseline cover rate
    cover_rate = compute_bayesian(
        historical_ats_df["Game Count"],
        historical_ats_df["Cover Rate"],
        0.5,
        m=m,
    )

    # Get the Bayesian adjusted win rate for each spread value
    # Using the fitted exponential function as the baseline
    win_rate = compute_bayesian(
        historical_ats_df["Game Count"],
        historical_ats_df["Raw Win Rate"],
        win_prob_function(historical_ats_df["Closing Spread"].astype(int).values, k),
        m=m,
    )

    historical_ats_df["Spread to Cover Win Diff"] = cover_rate - win_rate
    historical_ats_df.set_index("Closing Spread")["Spread to Cover Win Diff"].to_json(
        SPREAD_LOOKUP_PATH, orient="index", indent=2
    )


if __name__ == "__main__":
    main()
