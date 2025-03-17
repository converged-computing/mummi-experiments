#!/usr/bin/env python3

import random
import argparse
import json
import os
import re
import tarfile

from datetime import datetime

import matplotlib.pylab as plt
import pandas
import seaborn as sns

here = os.path.abspath(__file__)
root = os.path.dirname(here)

timestamp_format = "%Y-%m-%dT%H:%M:%SZ"
node_timestamp_format = "%Y-%m-%dT%H:%M:%S.%fZ"


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
    sm_indir = os.path.join(indir, "state-machine-operator-autoscale", "results")
    flux_sm_indir = os.path.join(indir, "state-machine-flux", "results", "processed")
    indirs = [mummi_indir, sm_indir, flux_sm_indir]
    times_df = parse_pulling_times(indirs)
    plot_pulling_times(times_df, outdir)

    # Now let's count outputs (total and excess)
    count_outputs(indirs, outdir, completions=args.completions)

    # Now look at times for the workflow manager
    workflow_times, workflow_starts, workflow_ends = workflow_manager(indirs, outdir)

    # Now let's look at times for jobs
    best_df = job_timings(indirs, outdir, workflow_times)
    calculate_costs(
        indirs, times_df, workflow_times, workflow_starts, workflow_ends, outdir
    )


def workflow_manager(indirs, outdir):
    """
    Look at timings for the workflow manager
    """
    # Keep a lookup for the exact workflow start timestamps
    workflow_starts = {}
    workflow_ends = {}
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
    print("See workflow running time to get 10 samples")
    print(workflow_times.groupby(["experiment", "global"]).duration.mean())
    print(total_time)
    return workflow_times, workflow_starts, workflow_ends


def combine_data_frames(indirs, filename):
    """
    Given indirs, where mummi is first and state machine
    second, combine into one data frame
    """
    mummi = pandas.read_csv(os.path.join(indirs[0], filename), index_col=0)
    sm = pandas.read_csv(os.path.join(indirs[1], filename), index_col=0)
    sm_flux = pandas.read_csv(os.path.join(indirs[2], filename), index_col=0)
    mummi["operator"] = "mummi"
    sm["operator"] = "state-machine"
    sm_flux["operator"] = "flux-state-machine"
    combined = pandas.concat([mummi, sm, sm_flux])
    # Save initial name for later backup
    combined["environment"] = combined["experiment"]
    combined["experiment"] = [
        x.replace("-static", "").replace("flux-", "")
        for x in combined["experiment"].tolist()
    ]
    combined["experiment"] = combined["operator"] + "-" + combined["experiment"]
    return combined


def find_mlrunner_times():
    """
    We can get the runtimes of the mlrunner on each GPU/CPU instance from the flux logs.
    """
    times = {"cpu": [], "gpu": []}
    mlrunner_gpu = [
        x
        for x in find_inputs(
            os.path.join(root, "state-machine-flux", "results", "gpu"), "out"
        )
        if "error" not in x and "mlrunner" in x
    ]
    mlrunner_cpu = [
        x
        for x in find_inputs(
            os.path.join(root, "state-machine-flux", "results", "cpu"), "out"
        )
        if "error" not in x and "mlrunner" in x
    ]
    for filename in mlrunner_gpu + mlrunner_cpu:
        content = read_file(filename)
        # Already seen is a message that we see when there is an invalid sample (and it runs again)
        # We only want to get times for one valid sample run
        if "Already seen" in content:
            continue
        # We only count valid samples (exit code 0). Technically the jobs
        flux_event = json.loads(
            [x for x in content.split("\n") if "complete" in x and "status" in x][0]
        )
        if flux_event["context"]["status"] != 0:
            continue
        # Get the two wrapping timestamps
        run_start = json.loads(
            [x for x in content.split("\n") if "shell.start" in x][0]
        )["timestamp"]
        run_end = json.loads(
            [x for x in content.split("\n") if "shell.task-exit" in x][0]
        )["timestamp"]
        environ = "cpu" if "cpu" in filename else "gpu"
        times[environ].append(run_end - run_start)
    return times


def job_timings(indirs, outdir, workflow_times):
    """
    Find output files for job timings.
    """
    function_times = combine_data_frames(indirs, "function-individual-times.csv")
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
    # For now fill in MuMMI iteration as 1 - we just have one run
    workflow_times.loc[workflow_times.operator == "mummi", "iteration"] = 1
    function_times.loc[function_times.operator == "mummi", "iteration"] = 1

    # Compare the actual workflow time with the theoretical minimum
    # Note that we won't have this for mummi, so we instead use the mean time of a single mummi run and multiply the runs needed
    # First find the mlrunner saves we have (from flux) that reflect mummi runs on the corresponding instance types
    mlrunner_single_times = find_mlrunner_times()
    mlrunner_times = workflow_times[workflow_times["global"] == "mlrunner_success"]
    createsim_times = function_times[function_times["global"] == "createsim_runtime"]
    cganalysis_times = function_times[function_times["global"] == "cganalysis_run"]

    # For each of gpu and cpu, randomly select 10 samples for MuMMI, which doesn't have the actual times
    # because we were running a server
    idx = mlrunner_times.shape[0] + 1
    mlrunner_cpu_sample = random.sample(mlrunner_single_times["cpu"], 10)
    mlrunner_gpu_sample = random.sample(mlrunner_single_times["gpu"], 10)
    for i in range(10):
        mlrunner_times.loc[idx, :] = [
            "mummi-cpu",
            "mlrunner_success",
            mlrunner_cpu_sample[i],
            "global",
            "mummi",
            i,
            "cpu-static",
        ]
        idx += 1
        mlrunner_times.loc[idx, :] = [
            "mummi-gpu",
            "mlrunner_success",
            mlrunner_gpu_sample[i],
            "global",
            "mummi",
            i,
            "gpu-static",
        ]
        idx += 1

    # Calculate the hypothetical bests for each iteration and experiment - if we just ran 10 completions of each job
    best_possible_times = {}
    for experiment in function_times.experiment.unique():
        if experiment not in best_possible_times:
            best_possible_times[experiment] = {}
        subset = function_times[function_times.experiment == experiment]
        for iteration in subset.iteration.unique():
            # The best possible time is 10 of each of createsim, cganalysis, and mlrunner
            createsim_best = (
                createsim_times[
                    (createsim_times.experiment == experiment)
                    & (createsim_times.iteration == iteration)
                ]
                .duration[0:10]
                .tolist()
            )
            cganalysis_best = (
                cganalysis_times[
                    (cganalysis_times.experiment == experiment)
                    & (cganalysis_times.iteration == iteration)
                ]
                .duration[0:10]
                .tolist()
            )
            mlrunner_best = (
                mlrunner_times[
                    (mlrunner_times.experiment == experiment)
                    & (mlrunner_times.iteration == iteration)
                ]
                .duration[0:10]
                .tolist()
            )
            # The best possible time is sum of 10 samples, divided by (distributed across) six nodes that are running
            best_possible_time = (
                sum(createsim_best) + sum(cganalysis_best) + sum(mlrunner_best)
            ) / 6
            best_possible_times[experiment][iteration] = best_possible_time

    workflow_complete_times = workflow_times[
        workflow_times["global"].isin(["workflow_complete", "wfmanager_run_workflow"])
    ]
    workflow_complete_times["global"] = "workflow_complete"
    workflow_complete_times["environment"] = [
        x.replace("-static", "") for x in workflow_complete_times["environment"]
    ]

    # Now let's compare to actual orchestration time.
    best_df = pandas.DataFrame(
        columns=[
            "experiment",
            "operator",
            "environment",
            "iteration",
            "actual_duration",
            "best_duration",
        ]
    )
    idx = 0
    for experiment, best_times in best_possible_times.items():
        workflow_actual_times = workflow_complete_times[
            workflow_complete_times.experiment == experiment
        ]
        for iteration, best_time in best_times.items():
            # There is only one operator per experiment
            operator = (
                workflow_complete_times[
                    workflow_complete_times.experiment == experiment
                ]
                .operator.unique()
                .tolist()[0]
            )
            environ = "cpu" if "cpu" in experiment else "gpu"
            actual_duration = workflow_actual_times[
                workflow_actual_times.iteration == iteration
            ].duration.values[0]
            best_df.loc[idx, :] = [
                experiment,
                operator,
                environ,
                iteration,
                actual_duration,
                best_time,
            ]
            idx += 1

    # Make a new label for the x axis that doesn't have gpu/cpu
    labels = [re.sub("(-?)(gpu|cpu)(-?)", "", x) for x in best_df.experiment.values]
    best_df["labels"] = labels

    # Finally! Make a plot!
    plt.figure(figsize=(7, 6))
    ax = sns.barplot(data=best_df, x="labels", y="actual_duration", hue="environment")
    sns.set_style("dark")
    sns.barplot(
        ax=ax,
        data=best_df,
        x="labels",
        y="best_duration",
        hue="environment",
        legend=None,
        alpha=0.5,
    )
    ax.set_xlabel("Experiment", fontsize=10)
    ax.set_ylabel("Workflow Total Time", fontsize=10)
    ax.set_xticklabels(ax.get_xmajorticklabels(), fontsize=14)
    ax.set_yticklabels(ax.get_yticks(), fontsize=14)
    # sns.move_legend(ax, "upper left", bbox_to_anchor=(1, 1))
    plt.title("Actual Time vs. Theoretical Best Time")
    plt.xticks(rotation=90)
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, f"actual-time-vs-theoretical.png"))
    plt.savefig(os.path.join(outdir, f"actual-time-vs-theoretical.svg"))
    plt.close()
    return best_df


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
                    job_end = parse_timestamp(item["events"]["completed"]["timestamp"])
                    job_start = parse_timestamp(
                        item["events"]["successfulcreate"]["timestamp"]
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
                    parsed_timestamp = parse_timestamp(timestamp)
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


def calculate_costs(workflow_times, outdir, best_df):
    """
    Calculate experiment costs based on timings.
    """
    # TODO: need to save workflow starts and stops as data somewhere, then load here
    times = workflow_times[
        workflow_times["global"].isin(["workflow_complete", "wfmanager_run_workflow"])
    ]
    times["global"] = "workflow_complete"
    times["environment"] = [x.replace("-static", "") for x in times["environment"]]
    # Add in hpc6a and p3dn costs
    cost_per_hour = [2.88 if "cpu" in x else 3.06 for x in times.experiment]
    times["cost_per_hour"] = cost_per_hour
    times["cost"] = times["cost_per_hour"] * (times["duration"] * 6 / 60 / 60)
    make_plot(
        times,
        title="Total Cost to Run Workflow",
        ydimension="cost",
        xdimension="environment",
        outdir=os.path.join(outdir, "img"),
        ext="png",
        plotname="workflow_total_cost",
        hue="operator",
        plot_type="bar",
        xlabel="Environment",
        ylabel="Cost ($)",
        rotation=360,
    )

    # The only meaningful comparison is the workflow running time to get 6 samples
    print("See workflow running time to get 6 samples")
    print(workflow_times.groupby(["experiment", "global"]).duration.mean())
    return workflow_times

    # TODO this is new stuff
    # def calculate_costs(
    #    indirs, nodes, times_df, manager_df, workflow_starts, workflow_ends, outdir
    # ):

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

    # Read in cluster nodes events
    cluster_nodes = {}
    for indir in indirs:
        experiment = get_experiment_name(indir)
        if experiment not in cluster_nodes:
            cluster_nodes[experiment] = {}
        iteration = get_experiment_iteration(indir)
        cluster_nodes[experiment][iteration] = read_json(
            os.path.join(indir, "cluster-nodes.json")
        )

    # Now use cluster nodes metadata to determine when nodes were up vs. note
    total_times = {}
    compute_nodes = ["hpc7g.16xlarge", "p3.2xlarge"]
    for experiment, iterset in cluster_nodes.items():
        if experiment not in total_times:
            total_times[experiment] = {}
        for iteration, nodeset in iterset.items():
            total_times[experiment][iteration] = []
            for node_name, nodemeta in nodeset.items():
                # Filter nodes to just include those that are for compute (not sticky)
                if (
                    nodemeta["labels"]["node.kubernetes.io/instance-type"]
                    not in compute_nodes
                ):
                    continue
                # While the experiment design doesn't elicit this, we need to check for the
                # case that a node went away and came up during the experiment. This might
                # happen with an aggressive autoscaling policy.
                first_event = nodemeta["conditions"][0]["last_transition_time"]

                # By default we know the node is up at the start of the workfow
                # Check that the first event was before the cluster was created
                node_start_time = workflow_starts[experiment][iteration]

                # Did the node report ready the first time after the experiment started?
                if first_event > node_start_time:
                    print(f"Found node {node_name} that came up during experiment")
                    node_start_time = first_event

                # If the last event posted had the node not ready, it was removed at some point.
                if not nodemeta["is_ready"]:
                    last_event = nodemeta["conditions"][-1]
                    assert (
                        last_event["type"] == "Ready" and last_event["status"] is False
                    )
                    node_uptime = last_event["last_transition_time"] - node_start_time
                    total_times[experiment][iteration].append(node_uptime)
                # If the node remained ready, it was up the duration of the experiment
                else:
                    total_times[experiment][iteration].append(
                        workflow_ends[experiment][iteration] - node_start_time
                    )

    # Sanity check!
    print(json.dumps(total_times, indent=4))

    # Now add up each to get the total experiment cost
    total_costs = {}
    for experiment, iterations in total_times.items():
        if experiment not in total_costs:
            total_costs[experiment] = {}
        for iteration, uptimes in iterations.items():
            total_costs[experiment][iteration] = {}
            if "cpu" in experiment:
                total_costs[experiment][iteration] = (sum(uptimes) / 60 / 60) * 1.683
            else:
                total_costs[experiment][iteration] = (sum(uptimes) / 60 / 60) * 3.06

    print(json.dumps(total_costs, indent=4))
    cost_df = pandas.DataFrame(
        columns=["experiment", "cost", "environment", "iteration"]
    )
    idx = 0
    for experiment, iterations in total_costs.items():
        for iteration, cost in iterations.items():
            environ = "autoscale"
            if "static" in experiment:
                environ = "static"
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
