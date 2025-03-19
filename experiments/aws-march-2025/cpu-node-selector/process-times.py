#!/usr/bin/env python3

import argparse
import json
import os
import re
import tarfile

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


def read_tarfile(filename):
    """
    Reads a .tar.gz file from a byte string and returns a dictionary
    where keys are file names and values are file contents as byte strings.
    """
    file_contents = {}
    with tarfile.open(filename, "r:gz") as tar:
        for member in tar.getmembers():
            if member.isfile():
                file_contents[member.name] = tar.extractfile(member).read()
    return file_contents


def find_inputs(input_dir, pattern="*.out"):
    """
    Find inputs (times results files)
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

    # Parse times for pulling containers
    createsims = find_inputs(indir, "createsims-times.json")

    # Now let's look at times for jobs
    job_timings(createsims, outdir)


def job_timings(samples, outdir):
    """
    Find output files for job timings.
    """
    # global is the function in absence of an iteration identifier
    df = pandas.DataFrame(
        columns=["instance", "iteration", "event", "duration", "global"]
    )
    idx = 0

    # These are functions that can be run more than once, and have an iteration id at the end
    multiple_runs = [
        "createsims_gromacs_energy_minimization",
        "createsims_gromacs_make_ndx",
        "createsims_generate_velocities",
        "createsims_short_equilibration",
        "createsims_pull_molecules",
        "createsims_mdrun_lipids_water",
        "createsims_trjconv_lipids_water",
    ]

    for sample in samples:
        times = json.loads(read_file(sample))
        instance = os.path.basename(os.path.dirname(sample)).replace("createsim-", "")

        # Save all total durations
        for name, duration in times["times"].items():
            df.loc[idx, :] = [
                instance,
                sample,
                name,
                duration,
                name,
            ]
            idx += 1

        # For all timestamps, calculate start to complete
        for name, timestamp in times["timestamps"].items():
            if "_start" not in name:
                continue
            event = name.replace("_start", "")

            # We will sum these totals at the end.
            global_event = event.rsplit("_", 1)[0]
            if global_event not in multiple_runs:
                global_event = event

            complete_ts = f"{event}_complete"
            if complete_ts not in times["timestamps"]:
                print(f"Warning: missing completion marker for {event}")
                continue
            duration = times["timestamps"][complete_ts] - timestamp
            df.loc[idx, :] = [
                instance,
                sample,
                event,
                duration,
                global_event,
            ]
            idx += 1

    spot = ["spot" if "spot" in x else "on-demand" for x in df.iteration.tolist()]
    df["spot"] = spot
    new_instance_names = []
    for i, instance_name in enumerate(df.instance.tolist()):
        if spot[i] == "spot":
            instance_name = f"{instance_name}-spot"
            print(instance_name)
        new_instance_names.append(instance_name)

    df["instance"] = new_instance_names

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
        # We got spot instances for these
        "c7a-12xlarge-spot": 0.6458,
        "c7g-16xlarge-spot": 0.5415,
        "m6g-16xlarge-spot": 0.6519,
        "c6in-12xlarge-spot": 0.8272,
    }

    costs = [lookup[x] for x in df.instance.tolist()]
    df["hourly_cost"] = costs

    # Calculate costs based on time
    df["hours"] = df["duration"] / 60 / 60
    df["cost"] = df["hours"] * df["hourly_cost"]

    img_outdir = os.path.join(outdir, "img")
    if not os.path.exists(img_outdir):
        os.makedirs(img_outdir)

    # Let's just look at total running time
    subset = df[df.event == "createsim_runtime"]

    # These were used for testing, randomly take 3 samples (the times are all the same so it doesn't matter)
    # c7a-12xlarge 12 runs, spot of the same is 7
    filtered = subset[~subset.instance.isin(["c7a-12xlarge", "c7a-12xlarge-spot"])]
    c7a_df = subset[subset.instance.isin(["c7a-12xlarge"])]
    c7a_spot_df = subset[subset.instance.isin(["c7a-12xlarge-spot"])]
    c7a_df = c7a_df.sample(n=3)
    c7a_spot_df = c7a_spot_df.sample(n=3)
    subset = pandas.concat([filtered, c7a_df, c7a_spot_df])

    # Normalize costs
    # subset["normalized_cost"] = subset["cost"] = subset["cost"].mean()
    order = [
        "c7g-16xlarge-spot",
        "m6g-16xlarge-spot",
        "c7a-12xlarge-spot",
        "hpc7g-16xlarge",
        "c6in-12xlarge-spot",
        "c7g-16xlarge",
        "c7a-12xlarge",
        "m6g-16xlarge",
        "c6in-12xlarge",
        "hpc6a-48xlarge",
        "r7iz-8xlarge",
        "m6a-16xlarge",
    ]

    # Did not go in this direction
    # plt.figure(figsize=(8, 6))
    # sns.lineplot(x=x, y=y, data=subset, hue="instance")
    # sns.boxplot(x=x, y="cost", data=subset, order=order, hue="instance") #, marker='o', color='red')
    # plt.xlabel(xlabel)
    # plt.ylabel(ylabel)
    # plt.title("Cost of Createsims Run By Instance Type")
    # plt.savefig()

    print(subset.groupby(["instance"]).duration.mean())
    print(subset.groupby(["instance"]).cost.mean())
    print(subset.groupby(["instance"]).count())
    make_plot(
        subset,
        title="Cost Per Createsims Run By Instance Type",
        ydimension="cost",
        xdimension="instance",
        outdir=img_outdir,
        ext="png",
        plotname="createsims_cost_by_instance",
        hue="spot",
        plot_type="box",
        xlabel="Instance Type",
        ylabel="Cost ($)",
        order=order,
        width=7,
        height=4,
    )
    df.to_csv(os.path.join(outdir, "createsim-timings.csv"))
    subset.to_csv(os.path.join(outdir, "createsim-total-times.csv"))
    
    # Generate figure for paper
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

    # Replace -spot in instance
    instance_names = [x.replace('-spot', '') for x in subset.instance.values]
    subset['instance_name'] = instance_names
    make_plot(
        subset,
        title="Cost Per Createsims Run By Instance Type",
        ydimension="cost",
        xdimension="instance_name",
        outdir=img_outdir,
        ext="png",
        plotname="createsims_cost_by_instance_type",
        hue="spot",
        plot_type="box",
        xlabel="Instance Type",
        ylabel="Cost ($)",
        order=order,
        width=7,
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
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, f"{plotname}.png"))
    plt.savefig(os.path.join(outdir, f"{plotname}.svg"))
    plt.clf()
    return ax


if __name__ == "__main__":
    main()
