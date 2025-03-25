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

timestamp_format = "%Y-%m-%dT%H:%M:%SZ"


def get_parser():
    parser = argparse.ArgumentParser(description="Times Explorer")
    parser.add_argument(
        "--root",
        help="root directory with experiment events metadata to parse",
        default=os.path.join(here, "monitor"),
    )
    parser.add_argument(
        "--out",
        help="directory to save parsed results (with experiment prefix)",
        default=os.path.join(here, "results"),
    )
    parser.add_argument(
        "--completions",
        help="completions expected for experiments",
        default=6,
        type=int,
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
    Find inputs (cganalysis output files)
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

    files = find_inputs(indir, "[.]out")

    # I developed this as I collected data, so the format is inconsistent.
    # We only saved files to log.out or named by -0.out.
    files = [x for x in files if "log.out" in x or "-0.out" in x]
    files = [x for x in files if "_data" not in x]

    # Now let's look at times for jobs
    job_timings(files, outdir)


def job_timings(samples, outdir):
    """
    Find output files for job timings.
    """
    # global is the function in absence of an iteration identifier
    df = pandas.DataFrame(columns=["instance", "simulation_ns", "sample", "spot"])
    idx = 0
    for sample in samples:
        content = read_file(sample)
        line = [x for x in content.split("\n") if "traj_comp" in x][-1]
        line = line.split("|")[-1]
        if "ns" not in line:
            raise ValueError(f"Unexpected line unit, {line}")
        print(line)
        simulation_ns = float(line.strip().split(" ")[0])
        instance = os.path.basename(os.path.dirname(sample)).replace("cganalysis-", "")
        spot_instance = "spot" if "spot" in sample else "on-demand"
        df.loc[idx, :] = [
            instance,
            simulation_ns,
            os.path.basename(os.path.dirname(os.path.dirname(sample))),
            spot_instance,
        ]
        idx += 1

    print(df.sort_values(["simulation_ns"]))
    df.to_csv(os.path.join(outdir, "simulation_ns_cganalysis.csv"))

    new_instance_names = []
    for row in df.iterrows():
        instance_name = row[1].instance
        if row[1].spot == "spot":
            instance_name = f"{row[1].instance}-spot"
            print(instance_name)
        new_instance_names.append(instance_name)
    df["instance_name"] = new_instance_names

    # Add in costs for each instance type
    lookup = {
        "hpc7g-16xlarge": 1.683,
        "c7g-16xlarge": 2.320,
        "m6g-16xlarge": 2.464,
        "c7a-12xlarge": 2.463,
        "c6in-12xlarge": 2.722,
        "r7iz-8xlarge": 2.976,
        "m6a-16xlarge": 2.765,
        "hpc6a-48xlarge": 2.88,
        "p3-2xlarge": 3.06,
        # We got spot instances for these
        "c7a-12xlarge-spot": 0.6458,
        "c7g-16xlarge-spot": 0.5415,
        "m6a-16xlarge-spot": 0.8596,
        "m6g-16xlarge-spot": 0.6519,
        "c6in-12xlarge-spot": 0.8272,
        "r7iz-8xlarge-spot": 0.7677,
        "p3-2xlarge-spot": 0.3760,
    }

    costs = [lookup[x] for x in df.instance_name.tolist()]
    df["hourly_cost"] = costs

    # Now we assume that we ran for 30 minutes
    df["half_hour_cost"] = [x / 2 for x in costs]

    # Let's try to do simulation seconds
    
    # Calculate costs based on science accomplished
    # We want to calculate dollars per simulation ns
    df["cost_per_simulation_ns"] = df.half_hour_cost / df.simulation_ns

    img_outdir = os.path.join(outdir, "img")
    if not os.path.exists(img_outdir):
        os.makedirs(img_outdir)

    order = [
        "hpc7g-16xlarge",
        "c7g-16xlarge",
        "c7a-12xlarge",
        "m6g-16xlarge",
        "p3-2xlarge",
        "hpc6a-48xlarge",
        "m6a-16xlarge",
        "c6in-12xlarge",
        "r7iz-8xlarge",
    ]

    make_plot(
        df,
        title="Cost Per Simulation Nanosecond By Instance Type",
        ydimension="cost_per_simulation_ns",
        xdimension="instance",
        outdir=img_outdir,
        ext="png",
        plotname="cganalysis_cost_per_simulation_ns",
        hue="spot",
        plot_type="box",
        xlabel="Instance Type",
        ylabel="Cost ($)",
        order=order,
        width=7,
        height=3,
        rotation=45,
        remove_x=True,
    )
    df.to_csv(os.path.join(outdir, "cganlaysis-cost-per-simulation.csv"))

    order = [
        "c7g-16xlarge",
        "hpc7g-16xlarge",
        "c7a-12xlarge",
        "m6g-16xlarge",
        "p3-2xlarge",
        "hpc6a-48xlarge",
        "c6in-12xlarge",
        "r7iz-8xlarge",
        "m6a-16xlarge",
    ]

    # Look at total simulation ns
    make_plot(
        df,
        title="Gromacs Simulation NS By Instance Type",
        ydimension="simulation_ns",
        xdimension="instance",
        outdir=img_outdir,
        ext="png",
        plotname="cganalysis_progress_simulation_ns",
        hue="spot",
        plot_type="box",
        xlabel="Instance Type",
        ylabel="Simulation Progress in 30 Minutes (ns)",
        order=order,
        width=7,
        height=3,
        remove_x=True,
        rotation=45,
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
    remove_x=False,
):
    """
    Helper function to make common plots.
    """
    plotfunc = sns.boxplot
    plotfunc = sns.stripplot

    ext = ext.strip(".")
    plt.figure(figsize=(width, height))
    sns.set_style("dark")
    ax = plotfunc(
        x=xdimension,
        y=ydimension,
        hue=hue,
        order=order,
        data=df,
        linewidth=1,
        palette=palette,
    )
    ax.legend_.set_title(None)
    if do_log:
        plt.yscale("log")
    plt.title(title)
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.set_xticklabels(ax.get_xmajorticklabels(), fontsize=10)
    ax.set_yticklabels(ax.get_yticks(), fontsize=10)
    # sns.move_legend(ax, "upper left", bbox_to_anchor=(1, 1))
    plt.xticks(rotation=rotation)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))
    if remove_x:
        ax.set_xlabel(None)
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, f"{plotname}.png"))
    plt.savefig(os.path.join(outdir, f"{plotname}.svg"))
    plt.clf()
    return ax


if __name__ == "__main__":
    main()
