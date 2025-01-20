#!/usr/bin/env python3

import argparse
import collections
import json
import os
import re
import sys
from datetime import datetime

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


def find_inputs(input_dir):
    """
    Find inputs (times results files)
    """
    files = []
    for filename in recursive_find(input_dir, pattern="events-"):
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

    # Find input files (skip anything with test)
    files = find_inputs(indir)
    if not files:
        raise ValueError(f"There are no input files in {indir}")

    # Saves raw data to file
    times = parse_data(indir, outdir, files)

    # Parse them into data frame too.
    times_df = parse_times(times)
    plot_times(times_df, outdir)


def parse_time_pulled(time_pulled):
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


def parse_times(times):
    """
    Read events and turn into data frame with container pull times
    """
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
            "iteration",
            "environment",
        ]
    )
    idx = 0

    # STRATEGY:
    # pod will get us pulling times
    # job will get us completion times (success or fail)
    #   jobs that do not complete in some respect are sunk cost
    #   that will be reflected in the total cluster up/down time
    for experiment, items in times.items():
        for uid, item in items.items():
            # Skip non-pod and job events for now
            kind = item["kind"]
            if kind not in ["Pod", "Job"]:
                continue

            # This is a problem with AWS CNI, usually shows up on deletion I think
            if "failedcreatepodsandbox" in item["events"]:
                continue

            # The only experiment without a stated size is aws eks gpu, size 16
            iteration = item["iteration"]
            environment = item["environment"]
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
                    item["events"]["successfulcreate"]["timestamp"], timestamp_format
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
                    iteration,
                    environment,
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
                        iteration,
                        environment,
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
                    iteration,
                    environment,
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
                    iteration,
                    environment,
                ]
                idx += 1
    return df


def plot_times(df, outdir):
    """
    Given an output directory, plot image to show pull times.
    """
    # Let's first plot pull times
    subset = df[df.event == "pulled"]
    colors = sns.color_palette("hls", len(subset.experiment.unique()))
    hexcolors = colors.as_hex()
    experiments = list(subset.experiment.unique())
    experiments.sort()
    palette = collections.OrderedDict()
    for t in experiments:
        palette[t] = hexcolors.pop(0)
    img_outdir = os.path.join(outdir, "img")
    if not os.path.exists(img_outdir):
        os.makedirs(img_outdir)
    make_plot(
        subset,
        title="Total Container Pulling Time by Experiment",
        ydimension="duration",
        xdimension="experiment",
        outdir=img_outdir,
        ext="png",
        plotname="pull_times_by_experiment",
        hue="experiment",
        palette=palette,
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
    make_plot(
        subset,
        title="Job Times By Experiment",
        ydimension="duration",
        xdimension="job",
        outdir=img_outdir,
        ext="png",
        plotname="job_times_by_experiment",
        hue="experiment",
        palette=palette,
        plot_type="box",
        xlabel="Job",
        ylabel="Running Time (seconds)",
        # do_log=True,
        # With log, no ylimit
        # ylim=None,
    )

    costs = {}
    # here is calculating the total experiment costs
    # this is from eksctl logs - when we see "node-x" ready
    # 11:48:17 nodes ready
    # 15:00:51 last print of "waiting for nodegroup workers"
    ## elapsed is 4 hours
    start_time = datetime.strptime("11:48:17", "%H:%M:%S")
    end_time = datetime.strptime("15:00:51", "%H:%M:%S")

    # This was gpu run 1
    # This is the total number of hours for all nodes multiplied by price per hour by number of nodes
    gpu_manual_up_seconds = (end_time - start_time).seconds
    costs["gpu-manual"] = 3.06 * (gpu_manual_up_seconds / 60 / 60) * 6

    # This was gpu run 2
    start_time = datetime.strptime("17:39:52", "%H:%M:%S")
    end_time = datetime.strptime("19:48:18", "%H:%M:%S")
    gpu_up_seconds = (end_time - start_time).seconds
    costs["gpu"] = 3.06 * (gpu_up_seconds / 60 / 60) * 6

    # This was cpu run 1
    start_time = datetime.strptime("20:00:34", "%H:%M:%S")
    end_time = datetime.strptime("22:22:45", "%H:%M:%S")
    cpu_up_seconds = (end_time - start_time).seconds
    costs["cpu-manual"] = 2.88 * (cpu_up_seconds / 60 / 60) * 6
    print(costs)

    # Let's do summary of job times
    by_job = subset.groupby(["job", "experiment"])["duration"].sum()
    subset = df[df.event == "pulled"]
    by_pull = subset.groupby(["experiment"])["duration"].sum()
    print(by_job)
    print(by_pull)

    # This is manual and gross - I'm too lazy to do it programatically now
    # I want to go outside :)
    summary_df = pandas.DataFrame(columns=["experiment", "event", "duration"])
    idx = 0
    for entry in by_job.items():
        summary_df.loc[idx, :] = [entry[0][1], "running-" + entry[0][0], entry[1]]
        idx += 1
    for entry in by_pull.items():
        summary_df.loc[idx, :] = [entry[0], "pulled", entry[1]]
        idx += 1

    # Add the cost for the total cluster being up
    # This is multiplied by 6 for total nodes count
    summary_df.loc[idx, :] = ["gpu", "cluster-uptime", gpu_up_seconds * 6]
    idx += 1
    summary_df.loc[idx, :] = ["cpu-manual", "cluster-uptime", cpu_up_seconds * 6]
    idx += 1
    summary_df.loc[idx, :] = ["gpu-manual", "cluster-uptime", gpu_manual_up_seconds * 6]
    print(gpu_manual_up_seconds - gpu_up_seconds)

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

    # Now let's count result types
    result_counts = {}
    for name in ["createsim", "cganalysis", "[.]gro"]:
        results = list(recursive_find("data", name))
        if "gro" in name:
            name = "mlserver"
        # These were manual pushes by me
        if name == "cganalysis":
            results = [x for x in results if 'cganalysis-0' not in x]
        result_counts[name] = {}
        filtered = [x for x in results if "cpu" in x]
        result_counts[name]["cpu-manual"] = len(filtered)
        filtered = [x for x in results if "gpu/1" in x]
        result_counts[name]["gpu-manual"] = len(filtered)
        filtered = [x for x in results if "gpu/2" in x]
        result_counts[name]["gpu"] = len(filtered)
    print(result_counts)


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
    plt.figure(figsize=(7, 6))
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
    plt.xticks(rotation=90)
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, f"{plotname}.png"))
    plt.clf()
    return ax


def read_file(filename):
    with open(filename, "r") as fd:
        content = fd.read()
    return content


def write_json(obj, filename):
    with open(filename, "w") as fd:
        fd.write(json.dumps(obj, indent=4))


def parse_data(indir, outdir, files):
    # Assemble results across filenames - we will have mixing
    lookup = {}
    for filename in files:
        events = read_file(filename)
        sections = [x.strip() for x in events.split("\n") if x.strip()]

        # All unique events (reasons)
        # {'created',
        # 'killing',
        # 'noderegistrationcheckerdidnotrunchecks',
        # 'pulled',
        # 'pulling',
        # 'scalingreplicaset',
        # 'scheduled',
        # 'started',
        # 'successfulcreate'}

        iteration = int(os.path.basename(os.path.dirname(filename)))
        environ = os.path.basename(os.path.dirname(os.path.dirname(filename)))

        # Experiment lookup
        if environ == "cpu":
            experiment = "cpu-manual"
        elif environ == "gpu" and iteration == 1:
            experiment = "gpu-manual"
        else:
            experiment = "gpu"

        # We have to separate results by experiment
        if experiment not in lookup:
            lookup[experiment] = {}

        # For each file, create lookup with container uid
        for section in sections:
            try:
                section = json.loads(section)
            except:
                print(f"Skipping non json {section}")
                continue

            # Discarded events
            if "reason" not in section:
                continue

            # unique id
            uid = section["metadata"]["name"].rsplit(".", 1)[0]
            kind = section["involvedObject"]["kind"]
            if uid not in lookup[experiment]:
                lookup[experiment][uid] = {
                    "events": {},
                    "environment": environ,
                    "iteration": iteration,
                    "experiment": experiment,
                    "kind": kind,
                }
            reason = section["reason"].lower()

            # Use event time and fall back to first time
            timestamp = section.get("eventTime") or section["firstTimestamp"]

            # Get the container URI from pulling
            if reason == "pulling":
                lookup[experiment][uid]["container"] = (
                    section["message"].rsplit(" ", 1)[-1].strip('"')
                )
            instance = section["reportingInstance"]
            lookup[experiment][uid]["events"][reason] = {
                "timestamp": timestamp,
                "instance": instance,
            }

            # If pulled, there is extra metadata about what it calculated
            if reason == "pulled":
                lookup[experiment][uid]["events"][reason]["message"] = section[
                    "message"
                ]

    # This is the primary raw data we are interested in.
    raw_times_file = os.path.join(outdir, "raw-times.json")
    print(f"Saving raw container times to {raw_times_file}")
    write_json(lookup, raw_times_file)

    # Get unique containers to save
    containers = {x.get("container") for _, x in lookup.items() if x.get("container")}
    # This gives us unique containers
    containers_file = os.path.join(outdir, "unique-containers.json")
    print(f"Saving list of unique containers to {containers_file}")
    write_json(list(containers), containers_file)
    return lookup


if __name__ == "__main__":
    main()
