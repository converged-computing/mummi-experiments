#!/usr/bin/env python3

import random
import argparse
import json
import os
import re
import tarfile

from datetime import datetime

import sys

here = os.path.abspath(os.path.dirname(__file__))
root = os.path.dirname(here)
sys.path.insert(0, root)
import mummi_experiments as me

import matplotlib.pylab as plt
import pandas
import seaborn as sns

timestamp_format = "%Y-%m-%dT%H:%M:%SZ"
node_timestamp_format = "%Y-%m-%dT%H:%M:%S.%fZ"


def get_parser():
    parser = argparse.ArgumentParser(description="Times Explorer")
    parser.add_argument(
        "--out",
        help="directory to save parsed results (with experiment prefix)",
        default=os.path.join(here, "results"),
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
    indir = os.path.abspath(here)
    if not os.path.exists(outdir):
        os.makedirs(outdir)

    # Specific results for each study
    mummi_indir = os.path.join(indir, "mummi-operator", "results")
    sm_indir = os.path.join(indir, "state-machine-operator-autoscale", "results")
    flux_sm_indir = os.path.join(indir, "state-machine-flux", "results", "processed")
    indirs = [mummi_indir, sm_indir, flux_sm_indir]
    times_df = parse_pulling_times(indirs)
    me.plot_pulling_times(times_df, outdir)

    # Now let's count outputs (total and excess)
    count_outputs(indirs, outdir, completions=args.completions)

    # Now look at times for the workflow manager
    workflow_times = workflow_manager(indirs, outdir)

    # Now let's look at times for jobs
    best_df = job_timings(indirs, outdir, workflow_times)
    calculate_costs(indirs, workflow_times, outdir, best_df)


def get_operators_with_autoscale(total_time):
    """
    Add "autoscale" to be part of the operator
    """
    operators = []
    for row in total_time.iterrows():
        if "autoscale" in row[1].experiment:
            operators.append(f"{row[1].operator}-autoscale")
        else:
            operators.append(row[1].operator)
    return operators


def workflow_manager(indirs, outdir):
    """
    Look at timings for the workflow manager
    """
    workflow_times = combine_data_frames(indirs, "workflow-individual-times.csv")
    me.make_plot(
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
    operators = get_operators_with_autoscale(total_time)
    total_time.loc[:, "environment"] = [
        x.replace("-static", "").replace("-autoscale", "")
        for x in total_time["environment"]
    ]
    total_time.loc[:, "operator"] = operators
    me.make_plot(
        total_time,
        title="Total Time to Run Workflow",
        ydimension="duration",
        xdimension="operator",
        outdir=os.path.join(outdir, "img"),
        ext="png",
        plotname="workflow_total_time",
        hue="environment",
        plot_type="bar",
        xlabel="Environment",
        ylabel="Running Time (seconds)",
        rotation=90,
    )

    # The only meaningful comparison is the workflow running time to get 6 samples
    print("See workflow running time to get 10 samples")
    print(workflow_times.groupby(["experiment", "global"]).duration.mean())
    print(total_time)
    return workflow_times


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
            os.path.join(here, "state-machine-flux", "results", "gpu"), "out"
        )
        if "error" not in x and "mlrunner" in x
    ]
    mlrunner_cpu = [
        x
        for x in find_inputs(
            os.path.join(here, "state-machine-flux", "results", "cpu"), "out"
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
    me.make_plot(
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
    plt.savefig(os.path.join(outdir, "actual-time-vs-theoretical.png"))
    plt.savefig(os.path.join(outdir, "actual-time-vs-theoretical.svg"))
    plt.close()
    return best_df


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
    me.make_plot(
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

    me.make_plot(
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


def parse_pulling_times(indirs):
    """
    Read events and turn into data frame with container pull times
    """
    mummi_pulling_file = os.path.join(indirs[0], "container-pulling-times.json")
    sm_pulling_file = os.path.join(indirs[1], "container-pulling-times.json")
    sm_flux_pulling = pandas.read_csv(
        os.path.join(indirs[2], "container-pull-times.csv"), index_col=0
    )
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

    # Kubernetes Operators first
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
                    pulled_seconds = me.parse_time_pulled(time_pulled)

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
                    job_end = me.parse_timestamp(
                        item["events"]["completed"]["timestamp"]
                    )
                    job_start = me.parse_timestamp(
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
                    parsed_timestamp = me.parse_timestamp(timestamp)
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

    # Now add singularity
    for row in sm_flux_pulling.iterrows():
        df.loc[idx, :] = [
            # uid is usually associated with a specific job identifier, none here
            None,
            "singularity",
            row[1].job,
            "pulled",
            row[1].duration,
            row[1].container.replace("docker://", ""),
            f"flux-state-machine-{row[1].experiment}",
        ]
        idx += 1
    return df


def calculate_costs(indirs, workflow_times, outdir, best_df):
    """
    Calculate experiment costs based on timings.
    """
    # We name state-machine-autoscale to be state machine too, make it a key
    workflow_start_end_times = {
        "mummi": read_json(os.path.join(indirs[0], "workflow-endpoint-times.json")),
        "state-machine": read_json(
            os.path.join(indirs[1], "workflow-endpoint-times.json")
        ),
        "state-machine-autoscale": read_json(
            os.path.join(indirs[1], "workflow-endpoint-times.json")
        ),
        "state-machine-flux": read_json(
            os.path.join(indirs[2], "workflow-endpoint-times.json")
        ),
    }
    times = workflow_times[
        workflow_times["global"].isin(["workflow_complete", "wfmanager_run_workflow"])
    ]
    times.loc[:, "global"] = "workflow_complete"
    operators = get_operators_with_autoscale(times)
    times.loc[:, "environment"] = [
        x.replace("-static", "").replace("-autoscale", "") for x in times["environment"]
    ]
    times.loc[:, "operator"] = operators

    # Add in hpc6a and p3dn costs
    cost_per_hour = [2.88 if "cpu" in x else 3.06 for x in times.environment]
    times["cost_per_hour"] = cost_per_hour

    # Read in cluster nodes events (we only need this for autoscaling)
    cluster_nodes = {}
    nodes_files = me.find_inputs(os.path.dirname(indirs[1]), "cluster-nodes.json")

    # These were earlier (experiment / testing) studies
    nodes_files = [
        x for x in nodes_files if not re.search("(7-threads|timeout|no-autoscaling)", x)
    ]

    # We only need this calculation for autoscale
    nodes_files = [x for x in nodes_files if "autoscale" in x]
    for node_file in nodes_files:
        environ = "gpu" if "gpu" in node_file else "cpu"
        experiment = f"state-machine-autoscale-{environ}"
        if experiment not in cluster_nodes:
            cluster_nodes[experiment] = {}
        iteration = me.get_experiment_iteration(os.path.dirname(node_file))
        cluster_nodes[experiment][iteration] = me.read_json(node_file)

    # Now use cluster nodes metadata to determine when nodes were up vs. not
    # These are for the state machine operator autoscale
    total_times = {}
    compute_nodes = ["hpc7g.16xlarge", "p3.2xlarge"]
    for experiment, iterset in cluster_nodes.items():
        if experiment not in total_times:
            total_times[experiment] = {}
        for iteration, nodeset in iterset.items():
            # These iterations get read in as strings...
            iteration = str(iteration)
            total_times[experiment][iteration] = []
            for node_name, nodemeta in nodeset.items():
                # Filter nodes to just include those that are for compute (not sticky)
                if (
                    nodemeta["labels"]["node.kubernetes.io/instance-type"]
                    not in compute_nodes
                ):
                    continue
                experiment_name, environ = experiment.rsplit("-", 1)
                # While the experiment design doesn't elicit this, we need to check for the
                # case that a node went away and came up during the experiment. This might
                # happen with an aggressive autoscaling policy.
                node_start_time = nodemeta["conditions"][0]["last_transition_time"]
                workflow_start_time = workflow_start_end_times[experiment_name][
                    "starts"
                ][f"{environ}-autoscale"][str(iteration)]
                workflow_end_time = workflow_start_end_times[experiment_name]["ends"][
                    f"{environ}-autoscale"
                ][str(iteration)]

                # Did the node report ready the first time after the experiment started?
                # Note from V: I do not see any nodes like this.
                first_event = workflow_start_time
                if node_start_time > workflow_start_time:
                    print(f"Found node {node_name} that came up during experiment")
                    first_event = node_start_time

                # If the last event posted had the node not ready, it was removed at some point.
                if not nodemeta["is_ready"]:
                    last_event = nodemeta["conditions"][-1]
                    assert (
                        last_event["type"] == "Ready" and last_event["status"] is False
                    )
                    node_uptime = last_event["last_transition_time"] - first_event
                    total_times[experiment][iteration].append(node_uptime)
                # If the node remained ready, it was up the duration of the experiment
                else:
                    total_times[experiment][iteration].append(
                        workflow_end_time - first_event
                    )

    # Create entries for each iteration in static experiments
    for experiment in times.experiment.unique():
        if "autoscale" in experiment:
            continue
        subset = times[times.experiment == experiment]
        if experiment not in total_times:
            total_times[experiment] = {}
        for iteration in subset.iteration.unique():
            iter_df = subset[subset.iteration == iteration]
            # This needs to be just one row
            assert iter_df.shape[0] == 1
            workflow_duration = iter_df.duration.values[0]
            iteration_cost = [workflow_duration] * 6
            # The json dump will throw up on us if this isn't a string
            total_times[experiment][str(iteration)] = iteration_cost

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
        columns=["experiment", "operator", "cost", "environment", "iteration"]
    )
    idx = 0
    for experiment, iterations in total_costs.items():
        # Derive the operator for nice organization
        # This gets rid of cpu/gpu
        operator = experiment.rsplit("-", 1)[0]
        environ = experiment.rsplit("-", 1)[1]
        for iteration, cost in iterations.items():
            cost_df.loc[idx, :] = [
                experiment.replace("-", " "),
                operator,
                cost,
                environ,
                int(iteration),
            ]
            idx += 1

    cost_df.to_csv(os.path.join(outdir, "total-costs.csv"))
    me.make_plot(
        cost_df,
        title="Total Cost to Run Workflow",
        ydimension="cost",
        xdimension="operator",
        outdir=os.path.join(outdir, "img"),
        ext="png",
        plotname="workflow_total_cost",
        hue="environment",
        plot_type="bar",
        order=[
            "state-machine-autoscale",
            "state-machine",
            "flux-state-machine",
            "mummi",
        ],
        xlabel="Environment",
        ylabel="Cost ($)",
        rotation=90,
    )


if __name__ == "__main__":
    main()
