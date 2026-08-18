#!/usr/bin/env python3
"""
plot_histogram.py

Read the merged all_samples.summary.tsv and generate a stacked histogram
of the 'copies' column, split by 'pool_match' (TRUE vs FALSE).

Produces two PNGs:
  - a linear-scale histogram
  - a log10-scale histogram (copies data is typically heavily right-skewed,
    so the log view is usually the more useful/readable one)
"""

import argparse
import csv
import sys

import matplotlib
matplotlib.use("Agg")  # headless rendering, no display needed
import matplotlib.pyplot as plt
import numpy as np


def parse_args():
    p = argparse.ArgumentParser(description="Plot stacked histogram of copies by pool_match.")
    p.add_argument("--input", required=True, help="Path to all_samples.summary.tsv")
    p.add_argument("--output-linear", required=True, help="Output PNG path (linear x-axis).")
    p.add_argument("--output-log", required=True, help="Output PNG path (log10 x-axis).")
    p.add_argument("--bins", type=int, default=30, help="Number of histogram bins.")
    return p.parse_args()


def to_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    v = str(value).strip().lower()
    if v == "true":
        return True
    if v == "false":
        return False
    return None


def load_data(path):
    true_vals = []
    false_vals = []
    skipped = 0

    with open(path, newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            copies_raw = row.get("copies", "")
            match_raw = row.get("pool_match", "")

            try:
                copies = float(copies_raw)
            except (TypeError, ValueError):
                skipped += 1
                continue

            match = to_bool(match_raw)
            if match is None:
                skipped += 1
                continue

            if match:
                true_vals.append(copies)
            else:
                false_vals.append(copies)

    if skipped:
        sys.stderr.write(f"WARNING: skipped {skipped} row(s) with missing/invalid 'copies' or 'pool_match'\n")

    return np.array(true_vals), np.array(false_vals)


def plot_stacked_histogram(true_vals, false_vals, bins, output_path, log_scale=False, title_suffix=""):
    all_vals = np.concatenate([true_vals, false_vals]) if (len(true_vals) or len(false_vals)) else np.array([0, 1])

    if log_scale:
        # Avoid log(0); floor at 1 for binning purposes
        floor_val = 1
        true_plot = np.clip(true_vals, floor_val, None)
        false_plot = np.clip(false_vals, floor_val, None)
        all_plot = np.clip(all_vals, floor_val, None)
        bin_edges = np.logspace(np.log10(all_plot.min()), np.log10(all_plot.max()), bins + 1)
    else:
        true_plot = true_vals
        false_plot = false_vals
        bin_edges = np.linspace(all_vals.min(), all_vals.max(), bins + 1)

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.hist(
        [true_plot, false_plot],
        bins=bin_edges,
        stacked=True,
        label=[f"pool_match = True (n={len(true_vals)})", f"pool_match = False (n={len(false_vals)})"],
        color=["#34d399", "#fb7185"],
        edgecolor="white",
        linewidth=0.4,
    )

    if log_scale:
        ax.set_xscale("log")
        ax.set_xlabel("Copies (log scale)")
        ax.set_yscale("log")
        ax.set_ylabel("Count (log scale)")
    else:
        ax.set_xlabel("Copies")
        ax.set_ylabel("Count")
        
    ax.set_title(f"Distribution of Copies by pool_match{title_suffix}")
    ax.legend(frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def main():
    args = parse_args()

    true_vals, false_vals = load_data(args.input)

    if len(true_vals) == 0 and len(false_vals) == 0:
        sys.stderr.write("ERROR: no valid data found to plot.\n")
        sys.exit(1)

    plot_stacked_histogram(
        true_vals, false_vals, args.bins, args.output_linear,
        log_scale=False, title_suffix=" (linear scale)"
    )
    plot_stacked_histogram(
        true_vals, false_vals, args.bins, args.output_log,
        log_scale=True, title_suffix=" (log scale)"
    )

    sys.stderr.write(
        f"Wrote {args.output_linear} and {args.output_log} "
        f"(TRUE n={len(true_vals)}, FALSE n={len(false_vals)})\n"
    )


if __name__ == "__main__":
    main()