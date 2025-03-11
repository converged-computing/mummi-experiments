#!/usr/bin/env python3

import argparse
import json
import os
import re
import sys
import tarfile
import io

from datetime import datetime

import matplotlib.pylab as plt
import pandas
import seaborn as sns

here = os.path.abspath(__file__)
root = os.path.dirname(here)

timestamp_format = "%Y-%m-%dT%H:%M:%SZ"


def get_parser():
    parser = argparse.ArgumentParser(description="Times Explorer")
    parser.add_argument(
        "--out",
        help="directory to save parsed results (with experiment prefix)",
        default=os.path.join(root, "results"),
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
    indir = os.path.abspath(root)
    if not os.path.exists(outdir):
        os.makedirs(outdir)

    # Specific results for each study
    mummi_indir = os.path.join(indir, "mummi-operator", "results")
    sm_indir = os.path.join(indir, "state-machine-operator", "results")
    indirs = [mummi_indir, sm_indir]
    times_df = parse_pulling_times(indirs)
    summary_df = plot_pulling_times(times_df, outdir)

    #  workflow-individual-times.csv
    # img/			       workflow-summed-times.csv

    # Now let's count outputs (total and excess)
    count_outputs(indirs, outdir, completions=args.completions)

    # Now let's look at times for jobs
    job_timings(indirs, outdir)

    # Now look at times for the workflow manager
    workflow_manager(indirs, outdir)

    # TODO calculate costs, likely when we add autoscaling


def workflow_manager(indirs, outdir):
    """
    Look at timings for the workflow manager
    """
    workflow_times = combine_data_frames(indirs, "workflow-individual-times.csv")
    make_plot(
        workflow_times,
        title="Workflow Manager Accumulated Function Times",
        ydimension="duration",
        xdimension="global",
        outdir=os.path.join(outdir, "img"),
        ext="png",
        plotname="workflow_manager_times",
        hue="experiment",
        plot_type="box",
        xlabel="Function",
        ylabel="Running Time (seconds)",
        width=12,
        height=12,
    )

    # The times we actually care about are for the entire workflow, and we
    # have slightly different labels but they measure the same thing.
    total_time = workflow_times[
        workflow_times["global"].isin(["workflow_complete", "wfmanager_run_workflow"])
    ]
    total_time["global"] = "workflow_complete"
    total_time["environment"] = [
        x.replace("-static", "") for x in total_time["environment"]
    ]
    make_plot(
        total_time,
        title="Total Time to Run Workflow",
        ydimension="duration",
        xdimension="environment",
        outdir=os.path.join(outdir, "img"),
        ext="png",
        plotname="workflow_total_time",
        hue="operator",
        plot_type="bar",
        xlabel="Environment",
        ylabel="Running Time (seconds)",
        rotation=360,        
        height=3,
    )

    # The only meaningful comparison is the workflow running time to get 6 samples
    print("See workflow running time to get 6 samples")
    print(workflow_times.groupby(["experiment", "global"]).duration.mean())
    print(total_time)


def combine_data_frames(indirs, filename):
    """
    Given indirs, where mummi is first and state machine
    second, combine into one data frame
    """
    mummi = pandas.read_csv(os.path.join(indirs[0], filename), index_col=0)
    sm = pandas.read_csv(os.path.join(indirs[1], filename), index_col=0)
    mummi["operator"] = "mummi"
    sm["operator"] = "state-machine"
    combined = pandas.concat([mummi, sm])
    # Save initial name for later backup
    combined["environment"] = combined["experiment"]
    combined["experiment"] = [
        x.replace("-static", "") for x in combined["experiment"].tolist()
    ]
    combined["experiment"] = combined["operator"] + "-" + combined["experiment"]
    return combined


def job_timings(indirs, outdir):
    """
    Find output files for job timings.
    """
    function_times = combine_data_frames(indirs, "function-individual-times.csv")
    summed_times = combine_data_frames(indirs, "function-summed-times.csv")
    make_plot(
        function_times,
        title="Total Accumulated Function Times",
        ydimension="duration",
        xdimension="global",
        outdir=os.path.join(outdir, "img"),
        ext="png",
        plotname="function_times_by_experiment",
        hue="experiment",
        plot_type="box",
        xlabel="Function",
        ylabel="Running Time (seconds)",
        width=12,
        height=12,
    )


def count_outputs(indirs, outdir, completions=6):
    """
    Count number of outputs for analyses.
    """
    completed = combine_data_frames(indirs, "jobs-completed.csv")
    excess = combine_data_frames(indirs, "jobs-excess-completed.csv")
    img_outdir = os.path.join(outdir, "img")
    if not os.path.exists(img_outdir):
        os.makedirs(img_outdir)

    # Plot each
    make_plot(
        excess,
        title="Excess Jobs by Experiment",
        ydimension="count",
        xdimension="job",
        outdir=img_outdir,
        ext="png",
        plotname="excess_jobs_by_experiment",
        hue="experiment",
        plot_type="bar",
        xlabel="Job Step",
        ylabel="Excess Completed Jobs (count)",
        height=3,
        rotation=360,
    )

    make_plot(
        completed,
        title="Total Completed Jobs by Experiment",
        ydimension="count",
        xdimension="job",
        outdir=img_outdir,
        ext="png",
        plotname="completed_jobs_by_experiment",
        hue="experiment",
        plot_type="bar",
        xlabel="Job Step",
        ylabel="Jobs (count)",
    )

    # Save combined data to file
    excess.to_csv(os.path.join(outdir, "jobs-excess-completed.csv"))
    completed.to_csv(os.path.join(outdir, "jobs-completed.csv"))


def parse_time_pulled(time_pulled):
    """
    Parse string timestamp into seconds for pulling.
    """
    minutes = 0
    # First check for milliseconds, if reported in ms there aren't seconds or minutes
    if "ms" in time_pulled:
        return float(time_pulled.replace("ms", "", 1)) / 1000
    if "m" in time_pulled:
        minutes, rest = time_pulled.split("m", 1)
        minutes = int(minutes)
        time_pulled = rest
    seconds = float(time_pulled.rstrip("s"))
    return (minutes * 60) + seconds


def parse_pulling_times(indirs):
    """
    Read events and turn into data frame with container pull times
    """
    mummi_pulling_file = find_inputs(indirs[0], "container-pulling-times.json")[0]
    sm_pulling_file = find_inputs(indirs[1], "container-pulling-times.json")[0]
    mummi_pulling = read_json(mummi_pulling_file)
    sm_pulling = read_json(sm_pulling_file)

    # This is for containers
    df = pandas.DataFrame(
        columns=[
            "name",
            "kind",
            "job",
            "event",
            "duration",
            "container",
            "experiment",
        ]
    )
    idx = 0

    operator_times = {
        "mummi": mummi_pulling,
        "state-machine": sm_pulling,
    }
    # STRATEGY:
    # pod will get us pulling times
    # job will get us completion times (success or fail)
    #   jobs that do not complete in some respect are sunk cost
    #   that will be reflected in the total cluster up/down time
    for operator, times in operator_times.items():
        for experiment, items in times.items():
            # Add the operator name to the experiment
            experiment = f"{operator}-{experiment}"

            # Remove static to make labels shorter
            # All these experiments are static (at least for now)
            experiment = experiment.replace("-static", "")
            for uid, item in items.items():
                # Skip non-pod and job events for now
                kind = item["kind"]
                if kind not in ["Pod", "Job"]:
                    continue

                # This is a problem with AWS CNI, usually shows up on deletion I think
                if "failedcreatepodsandbox" in item["events"]:
                    continue

                # The only experiment without a stated size is aws eks gpu, size 16
                container = item.get("container")
                if not container and "pulled" in item["events"]:
                    container = (
                        re.search('["].*["]', item["events"]["pulled"]["message"])
                        .group()
                        .strip('"')
                    )

                # PULLING
                # We can do our own calculation based on timestamps here
                # These seem to be better in terms of granularity
                pulled_seconds = None
                running_seconds = None
                job = None

                # We can derive pull plus waiting from the message here
                # This is better data
                if "pulled" in item["events"] and pulled_seconds is None:
                    message = item["events"]["pulled"]["message"]
                    # If it's already pulled, don't count it
                    if "already present on machine" in message.lower():
                        continue
                    time_pulled = re.search("[(].*[)]", message)
                    time_pulled = time_pulled.group().split(" ")[0].replace("(", "")
                    # parse time pulled
                    pulled_seconds = parse_time_pulled(time_pulled)

                elif "pulling" in item["events"] and "pulled" in item["events"]:
                    start = item["events"]["pulling"]["timestamp"]
                    end = item["events"]["pulled"]["timestamp"]
                    parsed_end = datetime.strptime(end, timestamp_format)
                    parsed_start = datetime.strptime(start, timestamp_format)
                    elapsed = parsed_end - parsed_start
                    pulled_seconds = elapsed.seconds

                # We can't use "killing" to derive pod times, they don't show up
                # until the cluster deletion. Also note that "Completed" can be
                # success or error - we only know this from result data
                if kind == "Job":
                    # This is a sunk cost - a job started that didn't finish
                    if "completed" not in item["events"]:
                        continue
                    job_end = datetime.strptime(
                        item["events"]["completed"]["timestamp"], timestamp_format
                    )
                    job_start = datetime.strptime(
                        item["events"]["successfulcreate"]["timestamp"],
                        timestamp_format,
                    )
                    running_seconds = (job_end - job_start).seconds
                    job = uid.split("-")[0]

                elif kind == "Pod" and container is not None:
                    if "cganalysis" in container:
                        job = "cganalysis"
                    elif "createsim" in container:
                        job = "createsim"

                # parse all events for absolute timestamp
                # For these we want absolute timestamps to compare across
                # because we need to understand variation between nodes
                pod_events = ["pulled", "pulling", "scheduled", "created", "started"]
                job_events = ["successfulcreate", "completed"]
                for event_name in pod_events + job_events:
                    if event_name not in item["events"]:
                        continue
                    # For these, calculate a difference.
                    previous_event = {"created": "pulled", "started": "created"}
                    timestamp = item["events"][event_name]["timestamp"]
                    parsed_timestamp = datetime.strptime(timestamp, timestamp_format)
                    df.loc[idx, :] = [
                        uid,
                        kind,
                        job,
                        event_name + "-timestamp",
                        parsed_timestamp.timestamp(),
                        container,
                        experiment,
                    ]
                    idx += 1
                    if event_name in previous_event:
                        previous_timestamp = item["events"][previous_event[event_name]][
                            "timestamp"
                        ]
                        previous_timestamp = datetime.strptime(
                            previous_timestamp, timestamp_format
                        )
                        elapsed = parsed_timestamp - previous_timestamp
                        event_seconds = elapsed.seconds
                        df.loc[idx, :] = [
                            uid,
                            kind,
                            job,
                            event_name,
                            event_seconds,
                            container,
                            experiment,
                        ]
                        idx += 1
                    continue

                if pulled_seconds is not None:
                    df.loc[idx, :] = [
                        uid,
                        kind,
                        job,
                        "pulled",
                        pulled_seconds,
                        container,
                        experiment,
                    ]
                    idx += 1

                if running_seconds is not None:
                    df.loc[idx, :] = [
                        uid,
                        kind,
                        job,
                        "running",
                        running_seconds,
                        container,
                        experiment,
                    ]
                    idx += 1
    return df


def calculate_timings(summary_df, outdir):
    """
    Calculate experiment costs based on timings.
    TODO need to take costs into account
    """
    # Add the cost for the total cluster being up
    # This is multiplied by 6 for total nodes count
    summary_df.loc[idx, :] = ["gpu", "cluster-uptime", gpu_up_seconds * 6]
    idx += 1
    # summary_df.loc[idx, :] = ["cpu-manual", "cluster-uptime", cpu_up_seconds * 6]
    # idx += 1
    # summary_df.loc[idx, :] = ["gpu-manual", "cluster-uptime", gpu_manual_up_seconds * 6]
    # print(gpu_manual_up_seconds - gpu_up_seconds)

    summary_df.to_csv(os.path.join(outdir, "summary-times.csv"))
    make_plot(
        summary_df,
        title="Accumulated Times of Events Per Experiment",
        ydimension="duration",
        xdimension="event",
        outdir=img_outdir,
        ext="png",
        plotname="total_times_by_experiment",
        hue="experiment",
        palette=palette,
        plot_type="bar",
        xlabel="Event",
        ylabel="Total Time (seconds)",
        # do_log=True,
        # With log, no ylimit
        # ylim=None,
    )

    costs = {}

    # here is calculating the total experiment costs
    # this is from eksctl logs - when we see "node-x" ready
    # This was gpu run 2
    start_time = datetime.strptime("22:11:17", "%H:%M:%S")
    end_time = datetime.strptime("23:31:46", "%H:%M:%S")
    gpu_up_seconds = (end_time - start_time).seconds
    costs["gpu"] = 3.06 * (gpu_up_seconds / 60 / 60) * 6

    # This was cpu run 1
    # start_time = datetime.strptime("20:00:34", "%H:%M:%S")
    # end_time = datetime.strptime("22:22:45", "%H:%M:%S")
    # cpu_up_seconds = (end_time - start_time).seconds
    # costs["cpu-manual"] = 2.88 * (cpu_up_seconds / 60 / 60) * 6
    print(costs)


def plot_pulling_times(df, outdir):
    """
    Given an output directory, plot image to show pull times.
    """
    # Let's first plot pull times
    subset = df[df.event == "pulled"]
    # Don't account for already pulled
    subset = subset[subset.duration != 0]
    # Only include analysis containers
    subset = subset[
        subset.container.isin([x for x in subset.container.unique() if "mummi" in x])
    ]
    img_outdir = os.path.join(outdir, "img")
    if not os.path.exists(img_outdir):
        os.makedirs(img_outdir)
    make_plot(
        subset,
        title="State Machine Operator Container Pulling Times",
        ydimension="duration",
        xdimension="experiment",
        outdir=img_outdir,
        ext="png",
        plotname="pull_times_by_experiment",
        hue="experiment",
        plot_type="box",
        xlabel="Container",
        ylabel="Pull Time (seconds)",
        # do_log=True,
        # With log, no ylimit
        # ylim=None,
    )

    # Now let's look at time for each job
    # Let's first plot pull times
    subset = df[df.event == "running"]

    # IMPORTANT - this was an outlier that will mess up the plot, but it needs to be reported
    # It never actually finished.
    # createsim-structure-iter00-000000000001  Job  createsim  running    82583      None  gpu-static
    subset = subset[subset.duration != subset.duration.max()]

    make_plot(
        subset,
        title="State Machine Operator Job Times By Experiment",
        ydimension="duration",
        xdimension="job",
        outdir=img_outdir,
        ext="png",
        plotname="job_times_by_experiment",
        hue="experiment",
        plot_type="box",
        xlabel="Job",
        ylabel="Running Time (seconds)",
        # do_log=True,
        # With log, no ylimit
        # ylim=None,
    )

    # Let's do summary of job times
    by_job = subset.groupby(["job", "experiment"])["duration"].sum()
    subset = df[df.event == "pulled"]
    by_pull = subset.groupby(["experiment"])["duration"].sum()
    print(by_job)
    print(by_pull)

    # Convert into data frame
    summary_df = pandas.DataFrame(columns=["experiment", "event", "duration"])
    idx = 0
    for entry in by_job.items():
        summary_df.loc[idx, :] = [entry[0][1], "running-" + entry[0][0], entry[1]]
        idx += 1
    for entry in by_pull.items():
        summary_df.loc[idx, :] = [entry[0], "pulled", entry[1]]
        idx += 1

    # We will add costs to this based on workflow running time
    return summary_df


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
):
    """
    Helper function to make common plots.
    """
    plotfunc = sns.lineplot
    if plot_type == "violin":
        plotfunc = sns.violinplot
    elif plot_type == "box":
        plotfunc = sns.boxplot
    elif plot_type == "bar":
        plotfunc = sns.barplot

    ext = ext.strip(".")
    plt.figure(figsize=(width, height))
    sns.set_style("dark")
    if plot_type == "violin":
        ax = plotfunc(
            x=xdimension,
            y=ydimension,
            hue=hue,
            data=df,
            linewidth=0.8,
            palette=palette,
            marker="o",
        )
    elif plot_type == "bar":
        ax = plotfunc(
            x=xdimension, y=ydimension, hue=hue, data=df, linewidth=0.8, palette=palette
        )
    elif plot_type == "box":
        ax = plotfunc(
            x=xdimension,
            y=ydimension,
            hue=hue,
            data=df,
            linewidth=1.8,
            palette=palette,
            whis=[5, 95],
            dodge=True,
        )
    else:
        ax = plotfunc(
            x=xdimension,
            y=ydimension,
            hue=hue,
            data=df,
            linewidth=1.8,
            palette=palette,
            # whis=[5, 95],
            # dodge=True,
        )
        # This range is specifically for pulling times -
        # so the ranges are equivalent
        if ylim is not None:
            ax.set(ylim=ylim)

    if do_log:
        plt.yscale("log")
    plt.title(title)
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.set_xticklabels(ax.get_xmajorticklabels(), fontsize=14)
    ax.set_yticklabels(ax.get_yticks(), fontsize=14)
    # sns.move_legend(ax, "upper left", bbox_to_anchor=(1, 1))
    plt.xticks(rotation=rotation)
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, f"{plotname}.png"))
    plt.savefig(os.path.join(outdir, f"{plotname}.svg"))
    plt.clf()
    return ax


if __name__ == "__main__":
    main()
