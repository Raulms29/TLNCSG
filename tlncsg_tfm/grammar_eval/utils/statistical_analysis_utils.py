import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import pandas as pd
from scipy.stats import norm, t
from scipy import stats


def calc_run_scores(x):
    total_weight = x["Criterion Weight"].sum()
    overall = x["Weighted_Score"].sum() / total_weight
    supported = (
        np.nan
        if x["Supported_Score"].isna().all()
        else (x["Weighted_Supported"].sum() / total_weight)
    )
    return pd.Series({"Run_Overall_Score": overall, "Run_Supported_Score": supported})


def compute_parametric_ci(sample, confidence_level=0.95):
    alpha = 1 - confidence_level
    mean = float(np.mean(sample))
    std = float(np.std(sample, ddof=1)) if len(sample) > 1 else 0.0
    n = len(sample)
    if n > 30:
        z = norm.ppf(1 - alpha / 2)
        h = z * std / np.sqrt(n)
    else:
        t_value = t.ppf(1 - alpha / 2, n - 1)
        h = t_value * std / np.sqrt(n)
    return mean - h, mean + h


def plot_grouped_bars(
    models,
    grammars,
    means_dict,
    err_lower,
    err_upper,
    err_sym,
    ylabel,
    title,
    is_symmetric_err=False,
):
    sns.set_theme(
        style="whitegrid",
        rc={
            "axes.facecolor": "#F8F9FA",
            "grid.color": "#E9ECEF",
            "font.size": 13,
            "axes.labelsize": 15,
            "axes.titlesize": 18,
            "xtick.labelsize": 14,
            "ytick.labelsize": 13,
        },
    )
    fig, ax = plt.subplots(figsize=(16, 8))
    x = np.arange(len(models))
    width = 0.85 / len(grammars)
    multiplier = 0
    colors = sns.color_palette("pastel", len(grammars))
    for i, g in enumerate(grammars):
        offset = width * multiplier
        if is_symmetric_err:
            err = err_sym[g]
        else:
            err = [err_lower[g], err_upper[g]]

        ax.bar(
            x + offset,
            means_dict[g],
            width,
            label=g,
            yerr=err,
            capsize=4,
            color=colors[i],
            edgecolor="black",
            linewidth=0.5,
            error_kw={"elinewidth": 1.5, "capthick": 1.5, "ecolor": "#333333"},
        )
        multiplier += 1
    ax.set_ylabel(ylabel, fontweight="bold", labelpad=12)
    ax.set_title(title, fontweight="bold", pad=20, fontsize=18)
    ax.set_xticks(x + width * (len(grammars) - 1) / 2)
    ax.set_xticklabels(models, rotation=0, ha="center", fontweight="bold")
    ax.legend(
        title="Gramática",
        loc="best",
        frameon=True,
        fancybox=True,
        shadow=True,
        fontsize=11,
        title_fontsize=12,
    )
    ax.set_ylim(0, 1)
    sns.despine(left=True, bottom=False)
    ax.grid(axis="y", linestyle="--", alpha=0.7)
    ax.grid(axis="x", visible=False)
    plt.tight_layout()
    plt.show()


def highlight_sig(val):
    try:
        if float(val) < 0.05:
            return "font-weight: bold"
    except:
        pass
    return ""


def compute_margin(sample, confidence_level=0.95):
    sample = np.array(sample, dtype=float)
    if len(sample) == 0:
        return np.nan, np.nan
    alpha = 1 - confidence_level
    mean = float(np.mean(sample))
    std = float(np.std(sample, ddof=1)) if len(sample) > 1 else 0.0
    n = len(sample)
    if n > 30:
        z = norm.ppf(1 - alpha / 2)
        h = z * std / np.sqrt(n)
    else:
        t_value = t.ppf(1 - alpha / 2, n - 1)
        h = t_value * std / np.sqrt(n)
    return mean, h
