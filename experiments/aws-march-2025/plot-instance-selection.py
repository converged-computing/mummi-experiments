#!/usr/bin/env python3

import argparse
import json
import os
import re

import matplotlib.pylab as plt
import pandas
import seaborn as sns

root = os.path.abspath(os.path.dirname(__file__))

timestamp_format = "%Y-%m-%dT%H:%M:%SZ"

sns.set_theme(style="whitegrid", palette="muted")


def get_parser():
    parser = argparse.ArgumentParser(description="Times Explorer")
    parser.add_argument(
        "--out",
        help="directory to save parsed results (with experiment prefix)",
        default=os.path.join(root, "results"),
    )
    return parser


def read_file(filename):
    with open(filename, "r") as fd:
        content = fd.read()
    return content


def recursive_find(base, pattern="*.*"):
    """
    Recursively find and yield files matching a glob pattern.
    """
    for root, _, filenames in os.walk(base):
        for filename in filenames:
            if not re.search(pattern, filename):
                continue
            yield os.path.join(root, filename)


def read_json(filename):
    return json.loads(read_file(filename))


def write_json(obj, filename):
    with open(filename, "w") as fd:
        fd.write(json.dumps(obj, indent=4))


def main():
    parser = get_parser()
    args, _ = parser.parse_known_args()

    # Read in parsed data for cpu / gpu runs
    cs_df = pandas.read_csv(
        os.path.join(root, "cpu-node-selector", "results", "createsim-total-times.csv"),
        index_col=0,
    )
    cg_df = pandas.read_csv(
        os.path.join(
            root, "gpu-node-selector", "results", "cganlaysis-cost-per-simulation.csv"
        ),
        index_col=0,
    )
    plot_timings(cs_df, cg_df, args.out)


def plot_timings(cs_df, cg_df, outdir):
    """
    Generate single figure for experiments of instance selection
    """
    order = [
        "c7g-16xlarge",
        "m6g-16xlarge",
        "c7a-12xlarge",
        "hpc7g-16xlarge",
        "c6in-12xlarge",
        "hpc6a-48xlarge",
        "r7iz-8xlarge",
        "m6a-16xlarge",
    ]

    fig, axes = plt.subplots(2, 1, sharex=True, figsize=(10, 6))
    sns.set_style("whitegrid")
    sns.swarmplot(
        cs_df,
        linewidth=1,
        ax=axes[0],
        y="cost",
        x="instance",
        hue="spot",
        order=order,
        size=7,
    )
    axes[0].set_title("Automated Selection of Instance Types", fontsize=14)
    axes[0].set_ylabel("Simulation Setup Cost ($)", fontsize=12)

    sns.swarmplot(
        cg_df,
        ax=axes[1],
        linewidth=1,
        y="cost_per_simulation_ns",
        x="instance",
        hue="spot",
        order=order,
        size=7,
    )
    # axes[1].set_title("Gromacs Simulation NS By Instance Type", fontsize=14)
    axes[1].set_ylabel("Cost Per Simulation NS ($)", fontsize=12)
    axes[1].set_xlabel("", fontsize=12)

    # Remove legend title, don't need it
    for ax in axes:
        handles, labels = ax.get_legend_handles_labels()
        ax.legend(handles=handles, labels=labels)

    axes[1].get_legend().remove()
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "img", "instance-type-costs-combined.svg"))
    plt.clf()


if __name__ == "__main__":
    main()
