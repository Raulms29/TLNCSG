import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import glob
import os
import warnings
from scipy.stats import gaussian_kde

CRITERION_ORDER = [
    "Syntactic Correctness (Well-formedness)",
    "Semantic Faithfulness",
    "Structural Quality",
    "Hypothesis Quality",
    "Minimality and Non-redundancy",
    "Aggregation and Projection Correctness",
]


def resolve_target_dir(target_dir, base_dir="outputs/query_eval"):
    """
    Resolves the directory to use. If 'latest' is passed, it finds the most recently modified directory.
    """
    if target_dir.lower() == "latest":
        dirs = [
            os.path.join(base_dir, d)
            for d in os.listdir(base_dir)
            if os.path.isdir(os.path.join(base_dir, d))
        ]
        resolved_dir = max(dirs, key=os.path.getmtime)
        print(f"Using latest directory: {resolved_dir}")
    else:
        resolved_dir = target_dir
        print(f"Using directory: {resolved_dir}")
    return resolved_dir


def load_evaluation_data(target_dir, top_n=3):
    """
    Loads overall score data to determine the top N models, then loads the all_runs evaluation
    data for those specific models, safely handling split/headerless files.
    """
    # Load the overall scores to find the top N models
    overall_files = glob.glob(
        os.path.join(target_dir, "evaluation_model_mode_overall_*.csv")
    )

    # Ensure we don't pick up the 'partial' outputs if there's a finalized one, or just take the first
    overall_file = next(
        (f for f in overall_files if "partial" not in f),
        overall_files[0] if overall_files else None,
    )
    if not overall_file:
        raise FileNotFoundError(f"No overall score CSV found in {target_dir}")

    df_overall = pd.read_csv(overall_file)
    df_overall["Model_Variant"] = df_overall["Model"] + df_overall["Thinking"].apply(
        lambda x: str(x).lower() == "true"
    ).apply(lambda x: " (Think)" if x else "")

    # Sort by Weighted_Overall (or Overall_Score) and get top N
    sort_col = (
        "Weighted_Overall"
        if "Weighted_Overall" in df_overall.columns
        else "Overall_Score"
    )
    df_overall = df_overall.sort_values(by=sort_col, ascending=False)
    top_n_models = df_overall["Model_Variant"].head(top_n).tolist()
    print(f"Top {top_n} models based on {sort_col}: {', '.join(top_n_models)}")

    # Load all runs data
    all_runs_files = glob.glob(os.path.join(target_dir, "evaluation_all_runs_*.csv"))
    if not all_runs_files:
        raise FileNotFoundError(f"No all runs score CSVs found in {target_dir}")

    # Find headers first to handle chunks without columns safely
    expected_cols = None
    for f in all_runs_files:
        if "Model" in pd.read_csv(f, nrows=2).columns:
            expected_cols = pd.read_csv(f, nrows=0).columns.tolist()
            break

    if expected_cols is None:
        raise ValueError("Could not find headers in any of the all_runs CSV files.")

    dfs_runs = []
    for f in all_runs_files:
        if "Model" in pd.read_csv(f, nrows=2).columns:
            df = pd.read_csv(f)
        else:
            # File lacks headers, use correctly inferred columns
            df = pd.read_csv(f, header=None, names=expected_cols)
        dfs_runs.append(df)

    df_runs = pd.concat(dfs_runs, ignore_index=True)
    df_runs["Model_Variant"] = df_runs["Model"] + df_runs["Thinking"].apply(
        lambda x: str(x).lower() == "true"
    ).apply(lambda x: " (Think)" if x else "")

    # Filter runs to only top N models
    df_runs_top = df_runs[df_runs["Model_Variant"].isin(top_n_models)]

    return df_runs_top


def plot_histogram_per_criterion(df_runs_top):
    """
    Plots a Histogram for each unique Criterion found in the dataframe.
    """
    sns.set_theme(style="whitegrid")

    criteria = df_runs_top["Criterion"].unique()
    criteria = sorted(
        criteria,
        key=lambda x: CRITERION_ORDER.index(x) if x in CRITERION_ORDER else 999,
    )

    n_criteria = len(criteria)
    cols = 2
    rows = (n_criteria + cols - 1) // cols

    fig, axes = plt.subplots(rows, cols, figsize=(15, 5 * rows))
    axes = axes.flatten()

    for i, criterion in enumerate(criteria):
        ax = axes[i]
        data = df_runs_top[df_runs_top["Criterion"] == criterion]

        sns.histplot(
            data=data,
            x="Eval Score",
            hue="Model_Variant",
            multiple="dodge",
            shrink=0.8,
            ax=ax,
            bins=np.linspace(0, 1, 11),  # 10 bins between 0 and 1
        )

        ax.set_title(f"Histogram: {criterion}", fontsize=12)
        ax.set_xlabel("Evaluation Score")
        ax.set_ylabel("Count")
        ax.set_xlim(-0.025, 1.025)

    for j in range(len(criteria), len(axes)):
        fig.delaxes(axes[j])

    plt.tight_layout()
    plt.show()


def plot_kde_per_criterion(df_runs_top, bw_adjust=0.5):
    """
    Plots the Kernel Density Estimation for each unique Criterion found in the dataframe.
    """
    # Set plotting style
    sns.set_theme(style="whitegrid")

    # Get unique criteria, ordered by predefined order
    criteria = df_runs_top["Criterion"].unique()
    criteria = sorted(
        criteria,
        key=lambda x: CRITERION_ORDER.index(x) if x in CRITERION_ORDER else 999,
    )

    # Calculate grid dimensions
    n_criteria = len(criteria)
    cols = 2
    rows = (n_criteria + cols - 1) // cols

    fig, axes = plt.subplots(rows, cols, figsize=(15, 5 * rows))
    axes = axes.flatten()

    for i, criterion in enumerate(criteria):
        ax = axes[i]
        # Filter data for the current criterion
        data = df_runs_top[df_runs_top["Criterion"] == criterion]

        # Plot KDE
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=UserWarning)
            sns.kdeplot(
                data=data,
                x="Eval Score",
                hue="Model_Variant",
                fill=True,
                ax=ax,
                common_norm=False,
                bw_adjust=bw_adjust,
                alpha=0.3,
                warn_singular=False,
                cut=0,  # Evita que la KDE se extienda más allá de los datos
            )

        ax.set_title(f"KDE for Criterion: {criterion}", fontsize=12)
        ax.set_xlabel("Evaluation Score")
        ax.set_ylabel("Density")
        ax.set_xlim(-0.025, 1.025)

    # Hide any empty subplots
    for j in range(len(criteria), len(axes)):
        fig.delaxes(axes[j])

    plt.tight_layout()
    plt.show()


# def plot_cumulative_kde_per_criterion(df_runs_top, bw_adjust=0.5):
#     """Plots the Cumulative Kernel Density Estimation (CDF equivalent) for each unique Criterion."""
#     sns.set_theme(style="whitegrid")

#     # Get unique criteria, ordered by predefined order
#     criteria = df_runs_top["Criterion"].unique()
#     criteria = sorted(
#         criteria,
#         key=lambda x: CRITERION_ORDER.index(x) if x in CRITERION_ORDER else 999,
#     )

#     n_criteria = len(criteria)
#     cols = 2
#     rows = (n_criteria + cols - 1) // cols
#     fig, axes = plt.subplots(rows, cols, figsize=(15, 5 * rows))
#     axes = axes.flatten()

#     for i, criterion in enumerate(criteria):
#         ax = axes[i]
#         data = df_runs_top[df_runs_top["Criterion"] == criterion]
#         with warnings.catch_warnings():
#             warnings.simplefilter("ignore", category=UserWarning)
#             sns.kdeplot(
#                 data=data,
#                 x="Eval Score",
#                 hue="Model_Variant",
#                 fill=True,
#                 ax=ax,
#                 common_norm=False,
#                 cumulative=True,
#                 bw_adjust=bw_adjust,
#                 alpha=0.3,
#                 warn_singular=False,
#             )
#         ax.set_title(f"Cumulative KDE: {criterion}", fontsize=12)
#         ax.set_xlabel("Evaluation Score")
#         ax.set_ylabel("Cumulative Probability")

#     for j in range(len(criteria), len(axes)):
#         fig.delaxes(axes[j])
#     plt.tight_layout()
#     plt.show()


def plot_cumulative_kde_per_criterion(df_runs_top, bw_adjust=0.5):
    """Plots the Cumulative Kernel Density Estimation for bounded 0-1 data."""
    sns.set_theme(style="whitegrid")

    criteria = df_runs_top["Criterion"].unique()
    criteria = sorted(
        criteria,
        key=lambda x: CRITERION_ORDER.index(x) if x in CRITERION_ORDER else 999,
    )

    n_criteria = len(criteria)
    cols = 2
    rows = (n_criteria + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(15, 5 * rows))
    axes = axes.flatten()

    for i, criterion in enumerate(criteria):
        ax = axes[i]
        data = df_runs_top[df_runs_top["Criterion"] == criterion]

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=UserWarning)
            sns.kdeplot(
                data=data,
                x="Eval Score",
                hue="Model_Variant",
                fill=True,
                ax=ax,
                common_norm=False,
                cumulative=True,
                bw_adjust=bw_adjust,
                alpha=0.3,
                warn_singular=True,
                cut=0,  # Evita que la KDE se extienda más allá de los datos
            )

        ax.set_title(f"Cumulative KDE: {criterion}", fontsize=12)
        ax.set_xlabel("Evaluation Score (Scaled 0 to 1)")
        ax.set_ylabel("Cumulative Probability")
        ax.set_xlim(-0.025, 1.025)

    for j in range(len(criteria), len(axes)):
        fig.delaxes(axes[j])

    plt.tight_layout()
    plt.show()


def plot_overall_kde(df_runs_top, bw_adjust=0.5):
    """Plots a single General KDE combining all criteria to show the overall distribution signature of each model."""
    sns.set_theme(style="whitegrid")
    plt.figure(figsize=(10, 6))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        sns.kdeplot(
            data=df_runs_top,
            x="Eval Score",
            hue="Model_Variant",
            fill=True,
            common_norm=False,
            bw_adjust=bw_adjust,
            alpha=0.3,
            warn_singular=False,
            cut=0,  # Evita que la KDE se extienda más allá de los datos
        )
    plt.title("Overall General KDE (All Criteria Aggregated)", fontsize=14)
    plt.xlabel("Evaluation Score")
    plt.ylabel("Density")
    plt.xlim(-0.025, 1.025)
    plt.tight_layout()
    plt.show()


import matplotlib.pyplot as plt
import seaborn as sns


def plot_overall_histogram(df_runs_top, bins=30):
    """Plots a single General Histogram combining all criteria to show the overall distribution of each model."""
    sns.set_theme(style="whitegrid")
    plt.figure(figsize=(10, 6))

    sns.histplot(
        data=df_runs_top,
        x="Eval Score",
        hue="Model_Variant",
        element="step",
        fill=True,
        stat="density",
        common_norm=False,
        alpha=0.3,
        bins=bins,
    )

    plt.title("Overall General Histogram (All Criteria Aggregated)", fontsize=14)
    plt.xlabel("Evaluation Score")
    plt.ylabel("Density")
    plt.xlim(-0.025, 1.025)
    plt.tight_layout()
    plt.show()


import matplotlib.pyplot as plt
import seaborn as sns


def plot_overall_cumulative_histogram(df_runs_top, bins=50):
    """Plots a single General Cumulative Histogram combining all criteria to show the overall distribution signature."""
    sns.set_theme(style="whitegrid")
    plt.figure(figsize=(10, 6))

    sns.histplot(
        data=df_runs_top,
        x="Eval Score",
        hue="Model_Variant",
        element="step",
        fill=True,
        stat="proportion",  # Cambiado a proporción para ir de 0 a 1
        cumulative=True,  # ¡Clave para que se acumule!
        common_norm=False,
        alpha=0.3,
        bins=bins,  # Controla la suavidad del escalón
    )

    plt.title("Overall Cumulative Distribution (All Criteria Aggregated)", fontsize=14)
    plt.xlabel("Evaluation Score")
    plt.ylabel("Cumulative Probability")
    plt.xlim(-0.025, 1.025)
    plt.tight_layout()
    plt.show()


import matplotlib.pyplot as plt
import seaborn as sns


def plot_cumulative_histogram_per_criterion(df_runs_top, bins=50):
    """Plots the Cumulative Histogram (CDF equivalent) for each unique Criterion without KDE."""
    sns.set_theme(style="whitegrid")

    # Obtener criterios únicos, ordenados por el orden predefinido
    criteria = df_runs_top["Criterion"].unique()
    criteria = sorted(
        criteria,
        key=lambda x: CRITERION_ORDER.index(x) if x in CRITERION_ORDER else 999,
    )

    n_criteria = len(criteria)
    cols = 2
    rows = (n_criteria + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(15, 5 * rows))
    axes = axes.flatten()

    for i, criterion in enumerate(criteria):
        ax = axes[i]
        data = df_runs_top[df_runs_top["Criterion"] == criterion]

        sns.histplot(
            data=data,
            x="Eval Score",
            hue="Model_Variant",
            element="step",  # Dibuja la línea de contorno sin barras internas
            fill=True,  # Rellena el área bajo la curva
            stat="proportion",  # Escala el eje Y de 0 a 1 (100% de los datos)
            cumulative=True,  # Suma los datos de izquierda a derecha
            common_norm=False,  # Calcula la proporción por cada modelo de forma independiente
            alpha=0.3,
            bins=bins,
            ax=ax,  # Asigna el gráfico al subplot correspondiente
        )

        ax.set_title(f"Cumulative Histogram: {criterion}", fontsize=12)
        ax.set_xlabel("Evaluation Score")
        ax.set_ylabel("Cumulative Probability")
        ax.set_xlim(-0.025, 1.025)

    # Eliminar subgráficos vacíos si el número de criterios es impar
    for j in range(len(criteria), len(axes)):
        fig.delaxes(axes[j])

    plt.tight_layout()
    plt.show()
