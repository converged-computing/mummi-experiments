#!/usr/bin/env python3

import argparse
import json
import os
import re
import tarfile

from datetime import datetime

import matplotlib.pylab as plt
import pandas
import seaborn as sns

here = os.path.abspath(os.path.dirname(__file__))
root = os.path.dirname(here)

timestamp_format = "%Y-%m-%dT%H:%M:%SZ"
node_timestamp_format = "%Y-%m-%dT%H:%M:%S.%fZ"


def get_parser():
    parser = argparse.ArgumentParser(description="Times Explorer")
    parser.add_argument(
        "--root",
        help="root directory with experiment events metadata to parse",
        default=os.path.join(here, "results"),
    )
    parser.add_argument(
        "--out",
        help="directory to save parsed results (with experiment prefix)",
        default=os.path.join(here, "results", "processed"),
    )
    parser.add_argument(
        "--completions",
        help="completions expected for experiments",
        default=10,
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
    img_outdir = os.path.join(outdir, "img")
    if not os.path.exists(img_outdir):
        os.makedirs(img_outdir)

    # Specific cpu and gpu results
    cpu_indirs = [
        os.path.join(indir, "cpu", x)
        for x in os.listdir(os.path.join(indir, "cpu"))
        if "error" not in x
    ]
    gpu_indirs = [
        os.path.join(indir, "gpu", x)
        for x in os.listdir(os.path.join(indir, "gpu"))
        if "error" not in x
    ]
    indirs = cpu_indirs + gpu_indirs

    # No container pulling here
    # Now let's count outputs (total and excess)
    count_outputs(indirs, outdir, completions=args.completions)

    # Now let's look at times for jobs
    job_timings(indirs, outdir)

    # Now look at times for the workflow manager
    manager_df, workflow_starts, workflow_ends = workflow_manager(indirs, outdir)
    calculate_costs(indirs, manager_df, workflow_starts, workflow_ends, outdir)


def calculate_costs(indirs, manager_df, workflow_starts, workflow_ends, outdir):

    # Make a data frame of just nodes
    workflow_times = {}
    for experiment in manager_df.experiment.unique():
        if experiment not in workflow_times:
            workflow_times[experiment] = {}
        subset = manager_df[manager_df.experiment == experiment]
        for iteration in subset.iteration.unique():
            # For one experiment, this is just one value
            workflow_times[experiment][iteration] = subset[
                (subset.iteration == iteration)
                & (manager_df["global"] == "workflow_complete")
            ].duration.mean()

    # calculate whole cost of experiment assuming all nodes up
    # (they were, because experiment is static)
    total_costs = {}
    for experiment, iterations in workflow_times.items():
        if experiment not in total_costs:
            total_costs[experiment] = {}
        for iteration, uptime in iterations.items():
            total_costs[experiment][iteration] = {}
            if "cpu" in experiment:
                total_costs[experiment][iteration] = (uptime / 60 / 60) * 1.683 * 6
            else:
                total_costs[experiment][iteration] = (uptime / 60 / 60) * 3.06 * 6

    print(json.dumps(total_costs, indent=4))
    cost_df = pandas.DataFrame(
        columns=["experiment", "cost", "environment", "iteration"]
    )
    idx = 0
    for experiment, iterations in total_costs.items():
        for iteration, cost in iterations.items():
            environ = "cpu"
            if "gpu" in experiment:
                environ = "gpu"
            cost_df.loc[idx, :] = [
                experiment.replace("-", " "),
                cost,
                environ,
                iteration,
            ]
            idx += 1

    cost_df.to_csv(os.path.join(outdir, "total-costs.csv"))
    make_plot(
        cost_df,
        title="Total Cost to Run Workflow",
        ydimension="cost",
        xdimension="experiment",
        outdir=os.path.join(outdir, "img"),
        ext="png",
        plotname="workflow_total_cost",
        hue="environment",
        plot_type="box",
        xlabel="Environment",
        ylabel="Cost ($)",
        rotation=360,
    )


def workflow_manager(indirs, outdir):
    """
    Look at timings for the workflow manager
    """
    # Keep a lookup for the exact workflow start timestamps
    workflow_starts = {}
    workflow_ends = {}
    df = pandas.DataFrame(
        columns=["experiment", "event", "duration", "global", "iteration"]
    )
    idx = 0
    for _indir in indirs:
        experiment = get_experiment_name(_indir)
        iteration = get_experiment_iteration(_indir)
        times = read_json(os.path.join(_indir, "workflow-times.json"))
        if experiment not in workflow_starts:
            workflow_starts[experiment] = {}
            workflow_ends[experiment] = {}
        if iteration not in workflow_starts[experiment]:
            workflow_starts[experiment][iteration] = {}
            workflow_ends[experiment][iteration] = {}
        for name, timestamp in times["timestamps"].items():
            if "workflow_start" in name:
                workflow_starts[experiment][iteration] = timestamp
                workflow_end = times["timestamps"]["workflow_complete"]
                workflow_ends[experiment][iteration] = workflow_end
                duration = workflow_end - timestamp
                df.loc[idx, :] = [
                    experiment,
                    name,
                    duration,
                    "workflow_complete",
                    iteration,
                ]
                idx += 1
                continue

            # Everything else should be a structure event, and we derive
            # other events (succeeded, failed) from that
            if "structure_" not in name or "_start" not in name:
                continue

            event = name.replace("_start", "")
            jobid, jobtype = event.rsplit("_", 1)

            # The job will either have failed or succeeded
            success_ts = f"{event}_succeeded"
            failure_ts = f"{event}_failed"
            if success_ts in times["timestamps"]:
                duration = times["timestamps"][success_ts] - timestamp
                df.loc[idx, :] = [
                    experiment,
                    jobtype,
                    duration,
                    f"{jobtype}_success",
                    iteration,
                ]
                idx += 1

            elif failure_ts in times["timestamps"]:
                duration = times["timestamps"][failure_ts] - timestamp
                df.loc[idx, :] = [
                    experiment,
                    jobtype,
                    duration,
                    f"{jobtype}_failure",
                    iteration,
                ]
                idx += 1

            else:
                print(
                    f"Warning, {name} started but did not succeed or fail, likely ran the whole time."
                )

    # Calculate sum totals for events. E.g., some functions are run multiple times
    # Note that this is across samples
    function_times = df.groupby(["experiment", "global", "iteration"])["duration"].sum()
    print(function_times)
    function_times = function_times.to_frame()

    # Make a more parseable data frame
    func_df = pandas.DataFrame(
        columns=["experiment", "function", "duration", "iteration"]
    )
    idx = 0
    for row in function_times.iterrows():
        func_df.loc[idx, :] = [row[0][0], row[0][1], row[1].duration, row[0][2]]
        idx += 1
    func_df.to_csv(os.path.join(outdir, "workflow-summed-times.csv"))

    # Save individual times too
    df.to_csv(os.path.join(outdir, "workflow-individual-times.csv"))

    # Remove functions that total sum across the workflow is < 1 second
    make_plot(
        df,
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
    total_time = df[df["global"].isin(["workflow_complete", "wfmanager_run_workflow"])]
    total_time["global"] = "workflow_complete"
    total_time["environment"] = [x.split("-")[1] for x in total_time["experiment"]]
    make_plot(
        total_time,
        title="Total Time to Run Workflow",
        ydimension="duration",
        xdimension="experiment",
        outdir=os.path.join(outdir, "img"),
        ext="png",
        plotname="workflow_total_time",
        hue="environment",
        plot_type="bar",
        xlabel="Environment",
        ylabel="Running Time (seconds)",
        rotation=360,
        height=3,
    )

    # The only meaningful comparison is the workflow running time to get 6 samples
    print("See workflow running time to get 10 completions")
    print(df.groupby(["experiment", "global"]).duration.mean())
    return df, workflow_starts, workflow_ends


def job_timings(indirs, outdir):
    """
    Find output files for job timings.
    """
    # global is the function in absence of an iteration identifier
    df = pandas.DataFrame(
        columns=[
            "experiment",
            "job",
            "sample",
            "event",
            "duration",
            "global",
            "iteration",
        ]
    )
    idx = 0
    for _indir in indirs:
        experiment = get_experiment_name(_indir)
        iteration = get_experiment_iteration(_indir)

        # This is the total number of samples that were pushed from mlserver
        samples = [
            x
            for x in find_inputs(_indir, "createsims-times.json")
            if "/createsim/" in x
        ]

        # Now we read in results via tarfile
        df, idx = parse_createsim_times(df, samples, experiment, idx, iteration)

        samples = [
            x
            for x in find_inputs(_indir, "cganalysis-times.json")
            if "/cganalysis/" in x
        ]
        df, idx = parse_cganalysis_times(df, samples, experiment, idx, iteration)

    # Calculate sum totals for events. E.g., some functions are run multiple times
    # Note that this is across samples and iterations within an experiment type
    function_times = df.groupby(["experiment", "global", "job", "iteration"])[
        "duration"
    ].sum()
    print(function_times)
    function_times = function_times.to_frame()

    # Make a more parseable data frame
    func_df = pandas.DataFrame(
        columns=["experiment", "function", "job", "duration", "iteration"]
    )
    idx = 0
    for row in function_times.iterrows():
        func_df.loc[idx, :] = [
            row[0][0],
            row[0][1],
            row[0][2],
            row[1].duration,
            row[0][3],
        ]
        idx += 1
    func_df.to_csv(os.path.join(outdir, "function-summed-times.csv"))

    # Save individual times too
    df.to_csv(os.path.join(outdir, "function-individual-times.csv"))

    make_plot(
        df,
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


def parse_createsim_times(df, samples, experiment, idx=0, iteration=0):
    """
    Parse timing output from createsims
    """
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
        sample_name = sample.split(os.sep)[-3]

        # Save all total durations
        for name, duration in times["times"].items():
            df.loc[idx, :] = [
                experiment,
                "createsim",
                sample_name,
                name,
                duration,
                name,
                iteration,
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
                experiment,
                "createsim",
                sample_name,
                event,
                duration,
                global_event,
                iteration,
            ]
            idx += 1
    return df, idx


def parse_timestamp(timestamp):
    """
    We either get an eventTime (considered atomic)
    or firstTimestamp (considered continuous). In practice
    I'm not sure the distinction makes sense, but the formats
    are slightly different.
    """
    if "." in timestamp:
        return datetime.strptime(timestamp, node_timestamp_format)
    return datetime.strptime(timestamp, timestamp_format)


def parse_cganalysis_times(df, samples, experiment, idx=0, iteration=0):
    """
    Parse timing output from cganalysis
    """
    for sample in samples:
        times = json.loads(read_file(sample))
        sample_name = sample.split(os.sep)[-3]

        # Save all total durations
        for name, duration in times["times"].items():
            df.loc[idx, :] = [
                experiment,
                "cganalysis",
                sample_name,
                name,
                duration,
                name,
                iteration,
            ]
            idx += 1

        # For all timestamps, calculate start to complete
        for name, timestamp in times["timestamps"].items():
            if "_start" not in name:
                continue
            event = name.replace("_start", "")
            complete_ts = f"{event}_complete"
            if complete_ts not in times["timestamps"]:
                print(f"Warning: missing completion marker for {event}")
                continue
            duration = times["timestamps"][complete_ts] - timestamp
            # cganalysis does not have loops, so no "global" events
            df.loc[idx, :] = [
                experiment,
                "cganalysis",
                sample_name,
                event,
                duration,
                event,
                iteration,
            ]
            idx += 1
    return df, idx


def get_experiment_iteration(indir):
    """
    The experiment iteration is the numerical suffix.
    """
    dirname = os.path.basename(indir)
    try:
        # We also start counting at 0
        iteration = int(dirname.split("-")[-1])
    except:
        raise ValueError(f"Issue getting iteration for {indir}")
    return iteration


def count_outputs(indirs, outdir, completions=10):
    """
    Count number of outputs for analyses.
    """
    # Note that excess here only includes completions, we don't account for
    # jobs that started running and didn't save output (partial run or otherwise)
    df = pandas.DataFrame(columns=["experiment", "job", "count", "iteration"])
    excess = pandas.DataFrame(columns=["experiment", "job", "count", "iteration"])
    idx = 0
    for _indir in indirs:
        experiment = get_experiment_name(_indir)
        iteration = get_experiment_iteration(_indir)
        # This is the total number of samples that were generated for mlserver
        samples = [x for x in find_inputs(_indir, "[.]gro") if "mlrunner" in x]
        # Let's use mlsamples to represent mlserver or mlrunner
        df.loc[idx, :] = [experiment, "mlsample", len(samples), iteration]
        excess.loc[idx, :] = [
            experiment,
            "mlsample",
            len(samples) - completions,
            iteration,
        ]
        idx += 1
        createsims = [
            x for x in find_inputs(_indir, "createsims.tar.gz") if "/createsim/" in x
        ]
        df.loc[idx, :] = [experiment, "createsim", len(createsims), iteration]
        excess.loc[idx, :] = [
            experiment,
            "createsim",
            len(createsims) - completions,
            iteration,
        ]
        idx += 1
        cganalysis = [
            x for x in find_inputs(_indir, "cganalysis") if "/cganalysis/" in x
        ]
        df.loc[idx, :] = [experiment, "cganalysis", len(cganalysis), iteration]
        excess.loc[idx, :] = [
            experiment,
            "cganalysis",
            len(cganalysis) - completions,
            iteration,
        ]
        idx += 1

    print("Experiment Job Counts (completed with results)")
    print(df)

    print("Excess Completed")
    print(excess)
    df.to_csv(os.path.join(outdir, "jobs-completed.csv"))
    excess.to_csv(os.path.join(outdir, "jobs-excess-completed.csv"))


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
    plt.savefig(os.path.join(outdir, f"{plotname}.svg"))
    plt.savefig(os.path.join(outdir, f"{plotname}.png"))
    plt.clf()
    return ax


def get_experiment_name(environ):
    if "cpu" in environ:
        return "flux-cpu"
    elif "gpu" in environ:
        return "flux-gpu"
    raise ValueError(f"Unknown environment {environ}")


def parse_events(outdir, files):
    """
    Parse events data for pulling containers.
    """
    # Assemble results across filenames - we will have mixing
    lookup = {}
    nodes = {}
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
        experiment = get_experiment_name(filename)

        # We have to separate results by experiment
        if experiment not in lookup:
            lookup[experiment] = {}
            nodes[experiment] = {}

        # For each file, create lookup with container uid
        for section in sections:
            try:
                section = json.loads(section)
            except:
                print(f"Skipping non json {section}")
                continue

            if "metadata" not in section:
                continue

            # unique id
            uid = section["metadata"]["name"].rsplit(".", 1)[0]
            kind = section["involvedObject"]["kind"]
            if kind == "Node":
                node_name = section["involvedObject"]["name"]
                if node_name not in nodes[experiment]:
                    nodes[experiment][node_name] = {}
                nodes[experiment][node_name][section["reason"]] = section[
                    "firstTimestamp"
                ]
                continue

            # Discarded events
            if "reason" not in section:
                continue

            if uid not in lookup[experiment]:
                lookup[experiment][uid] = {
                    "events": {},
                    "experiment": experiment,
                    "kind": kind,
                }
            reason = section["reason"].lower()

            # Use event time and fall back to first time
            # eventTime is of atomic event, firstTimestamp The first timestamp of a continuous one
            # In practice, I don't see eventTime for events I'd consider atomic.
            # Note they have different formats...
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
    raw_times_file = os.path.join(outdir, "container-pulling-times.json")
    print(f"Saving raw container times to {raw_times_file}")
    write_json(lookup, raw_times_file)
    return lookup, nodes


if __name__ == "__main__":
    main()
