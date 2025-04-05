#!/usr/bin/env python3

import argparse
import json
import os
import re

import matplotlib.ticker as mticker
import matplotlib.pylab as plt
import pandas
import seaborn as sns

here = os.path.abspath(os.path.dirname(__file__))
root = os.path.dirname(here)

from state_machine_operator.analysis.manager import (
    WorkflowTimesParser,
)
import state_machine_operator.analysis.plot as plot

timestamp_format = "%Y-%m-%dT%H:%M:%SZ"


def get_parser():
    parser = argparse.ArgumentParser(description="Times Explorer")
    parser.add_argument(
        "--root",
        help="root directory with experiment events metadata to parse",
        default=os.path.join(here, "data", "logs"),
    )
    parser.add_argument(
        "--out",
        help="directory to save parsed results (with experiment prefix)",
        default=os.path.join(here, "results"),
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


def find_inputs(input_dir, pattern="*.out"):
    """
    Find inputs (pytorch resnet output files)
    """
    files = []
    for filename in recursive_find(input_dir, pattern=pattern):
        # We only have data for small
        files.append(filename)
    return files


def read_json(filename):
    return json.loads(read_file(filename))


def write_json(obj, filename):
    with open(filename, "w") as fd:
        fd.write(json.dumps(obj, indent=4))


def main():
    parser = get_parser()
    args, _ = parser.parse_known_args()

    # Output images and data
    outdir = os.path.abspath(args.out)
    indir = os.path.abspath(args.root)
    if not os.path.exists(outdir):
        os.makedirs(outdir)

    # We want to plot accuracy over time, and we only want 0 index with logs of epochs
    files = find_inputs(indir, "0[.]out")
    files.sort()
    wftimes = find_inputs(os.path.dirname(indir), "workflow-times[.]json")

    # Parse workflow times
    parser = WorkflowTimesParser()
    for iteration, filename in enumerate(wftimes):
        parser.add_experiment(filename, "ml-mummi", iteration)

    img_outdir = os.path.join(outdir, "img")
    if not os.path.exists(img_outdir):
        os.makedirs(img_outdir)

    # Make human friendly labels without _
    parser.df["labels"] = [x.replace("_", " ") for x in parser.df.event.values]

    # Remove functions that total sum across the workflow is < 1 second
    plot.make_plot(
        parser.df,
        title="Workflow Manager Function Times",
        ydimension="duration",
        xdimension="labels",
        outdir=img_outdir,
        ext="png",
        plotname="workflow_manager_function_times",
        hue="experiment",
        plot_type="box",
        xlabel="Function",
        ylabel="Running Time (seconds)",
    )

    parser.df.to_csv(os.path.join(outdir, "workflow-times.csv"))

    # Parse epochs
    epocs = []
    job = []
    for filename in files:
        log = read_file(filename)
        iteration = int(filename.split(os.sep)[-2])
        accuracy = [float(x.split(" ")[-1]) for x in log.split("\n") if "Accuracy" in x]
        epocs += accuracy
        job += [iteration + 1] * len(accuracy)

    iters = list(range(len(epocs)))
    df = pandas.DataFrame()
    df["accuracy"] = epocs
    df["iters"] = iters
    df["jobset"] = job
    plot_accuracy(df, outdir)


def plot_accuracy(df, outdir):
    df.to_csv(os.path.join(outdir, "accuracy-by-epoch.csv"))
    plot.make_plot(
        df,
        title="Incremental Increase in Model Accuracy",
        ydimension="accuracy",
        xdimension="iters",
        outdir=os.path.join(outdir, "img"),
        ext="png",
        plotname="accuracy_by_epoch",
        hue="jobset",
        plot_type="box",
        xlabel="Epoch",
        ylabel="Accuracy",
        rotation=360,
        round_y=True,
        width=10,
        height=4,
    )
    make_plot(
        df,
        title="Incremental Increase in Model Accuracy",
        ydimension="accuracy",
        xdimension="iters",
        outdir=os.path.join(outdir, "img"),
        ext="svg",
        plotname="accuracy_by_epoch",
        hue="jobset",
        plot_type="box",
        xlabel="Epoch",
        ylabel="Accuracy",
        rotation=360,
        round_y=True,
        width=10,
        height=4,
    )


def make_plot(
    df,
    title,
    ydimension,
    xdimension,
    xlabel,
    ylabel,
    palette=None,
    ext="pdf",
    plotname="lammps",
    plot_type="violin",
    hue=None,
    outdir="img",
    do_log=False,
    ylim=None,
    rotation=90,
    width=7,
    height=6,
    order=None,
    remove_legend=False,
    remove_y=False,
    remove_x=False,
    round_y=False,
    xmin=None,
    xmax=None,
    ymin=None,
    ymax=None,
):
    """
    Helper function to make common plots.
    """
    ext = ext.strip(".")
    cmap = "Set2"
    fig, ax = plt.subplots(figsize=(width, height))
    sns.set_style("dark")
    sns.boxplot(
        x=xdimension,
        y=ydimension,
        ax=ax,
        data=df,
        linewidth=2.5,
        order=order,
        whis=[5, 95],
        dodge=True,
        width=0.3,
    )
    z = df.shape[0] * [df["jobset"].values]
    ax3 = sns.heatmap(z, ax=ax, cmap=cmap, cbar=False)
    ax3.set(yticklabels=[])
    ax3.axhline(0.7, ls="--", color="navy", linewidth=1)
    if do_log:
        plt.yscale("log")
    if remove_legend:
        ax.get_legend().set_title(None)
    plt.ylim(0, 1)
    ax.set_yticks([0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1])
    ax.set_yticklabels([0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1])
    plt.title(title)
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.set_xticklabels(ax.get_xmajorticklabels(), fontsize=10)
    ax.set_yticklabels(ax.get_yticks(), fontsize=10)
    # sns.move_legend(ax, "upper left", bbox_to_anchor=(1, 1))
    if remove_x:
        ax.set_xlabel(None)
    if remove_y:
        ax.set_ylabel(None)
        ax.set_yticks([])
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f"))
    plt.xticks(rotation=rotation)
    plt.yticks(rotation=rotation)
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, f"{plotname}.svg"))
    plt.savefig(os.path.join(outdir, f"{plotname}.png"))
    plt.clf()
    return ax


if __name__ == "__main__":
    main()
