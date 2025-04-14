#!/usr/bin/env python3

import copy
import random
import argparse
import json
import os
import re
import tarfile
import sys

here = os.path.abspath(os.path.dirname(__file__))
root = os.path.dirname(here)
sys.path.insert(0, root)
import mummi_experiments as me

import matplotlib.pylab as plt
import pandas
import seaborn as sns

sns.set_theme(style="whitegrid", palette="tab10")

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
    on_prem_indir = os.path.join(indir, "on-prem", "results")
    indirs = [mummi_indir, sm_indir, flux_sm_indir]
    times_df = parse_pulling_times(indirs, outdir)
    me.plot_pulling_times(times_df, outdir)

    # Now let's count outputs (total and excess)
    indirs.append(on_prem_indir)
    count_outputs(indirs, outdir, completions=args.completions)

    # Now look at times for the workflow manager
    workflow_times = workflow_manager(indirs, outdir)

    # Now let's look at times for jobs
    best_df = job_timings(indirs, outdir, workflow_times, times_df)

    # We can't calculate cost for on prem
    # indirs.pop()
    # workflow_times = workflow_times[workflow_times.experiment != 'on-premises-gpu']
    # best_df = best_df[best_df.experiment != 'on-premises-gpu']
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
    total_time["labels"] = derive_pretty_labels(total_time.operator.values)
    me.make_plot(
        total_time,
        title="Total Time to Run Workflow",
        ydimension="duration",
        xdimension="labels",
        outdir=os.path.join(outdir, "img"),
        ext="png",
        plotname="workflow_total_time",
        hue="environment",
        plot_type="bar",
        xlabel=None,
        ylabel="Running Time (seconds)",
        rotation=360,
        width=9,
        height=4,
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
    on_prem = pandas.read_csv(os.path.join(indirs[3], filename), index_col=0)
    mummi["operator"] = "mummi"
    sm["operator"] = "state-machine"
    sm_flux["operator"] = "flux-state-machine"
    on_prem["operator"] = "on-premises"
    combined = pandas.concat([mummi, sm, sm_flux, on_prem])
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


def derive_pretty_labels(values):
    """
    Ensure we replace - with spaces and add newlines
    to experiment names for better looking plots.
    """
    labels = [re.sub("(-?)(gpu|cpu)(-?)", "", x) for x in values]

    # I am bad at regular expressions
    labels = [x.replace("machineautoscale", "machine-autoscale") for x in labels]

    # Try adding newlines and spoces
    return [
        x.replace("-", " ")
        .replace("autoscale", "\nautoscale")
        .replace("flux", "flux\n")
        for x in labels
    ]


def job_timings(indirs, outdir, workflow_times, pull_df):
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

    # Make a plot for job times
    plot_job_times(mlrunner_times, createsim_times, outdir)

    # Calculate the hypothetical bests for each iteration and experiment - if we just ran 10 completions of each job
    # We also have to include container pulling, to be fair
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

            # Add the pulling time - we divide by 6 assuming that it is evenly distributed across nodes.
            # For autoscaling, this is OK because we just downsized. If we size up we would need to account for new pulls
            experiment_name = experiment
            if "autoscale" not in experiment:
                experiment_name = f"{experiment}-static"

            # Flux didn't pull containers
            if "flux" in experiment_name:
                pull_time = 0
                best_possible_times[experiment][iteration] = (
                    best_possible_time + pull_time
                )
                continue

            pull_time = (
                pull_df[
                    (pull_df.experiment == experiment_name)
                    & (pull_df.iteration == iteration)
                    & (pull_df.event == "pulled")
                ].duration.sum()
                / 6
            )
            best_possible_times[experiment][iteration] = best_possible_time + pull_time

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
    best_df["labels"] = derive_pretty_labels(best_df.experiment.values)

    # Finally! Make a plot!
    plt.figure(figsize=(9, 4))
    order = [
        "flux\n state machine",
        "state machine \nautoscale",
        "state machine",
        "mummi",
        "on premises",
    ]
    ax = sns.barplot(
        data=best_df, x="labels", y="actual_duration", hue="environment", order=order
    )
    sns.set_style("whitegrid")
    sns.barplot(
        ax=ax,
        data=best_df,
        x="labels",
        y="best_duration",
        hue="environment",
        legend=None,
        order=order,
        alpha=0.5,
    )
    ax.set_xlabel(None)
    ax.set_ylabel("Workflow Total Time", fontsize=10)
    ax.set_xticklabels(ax.get_xmajorticklabels(), fontsize=14)
    ax.set_yticklabels(ax.get_yticks(), fontsize=14)
    # sns.move_legend(ax, "upper left", bbox_to_anchor=(1, 1))
    plt.title("Actual Time vs. Theoretical Best Time")
    #    plt.xticks(rotation=90)
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "actual-time-vs-theoretical.png"))
    plt.savefig(os.path.join(outdir, "actual-time-vs-theoretical.svg"))
    plt.close()
    print("Theoretical Best Duration")
    print(best_df.groupby(["operator", "environment"]).best_duration.mean())
    print("Actual Duration")
    print(best_df.groupby(["operator", "environment"]).actual_duration.mean())
    return best_df


def plot_job_times(mlrunner_times, createsim_times, outdir):
    """
    We previously used the wrapper to jobs (e.g., running kubernetes pod)
    but for on premises we just have the recorded job times.
    """
    createsim_times["env"] = [
        x.rsplit("-", 1)[0] for x in createsim_times.environment.values
    ]
    createsim_times["label"] = [
        re.sub("-(gpu|cpu)", "", x).replace("-", " ")
        for x in createsim_times.experiment.values
    ]
    img_outdir = os.path.join(outdir, "img")
    me.make_plot(
        createsim_times,
        title="Createsim Times by Experiment",
        ydimension="duration",
        xdimension="env",
        outdir=img_outdir,
        ext="png",
        plotname="createsim_times_by_experiment",
        hue="label",
        palette=me.colors,
        plot_type="box",
        xlabel=None,
        ylabel="Duration (Seconds)",
        rotation=360,
        remove_x=True,
        order=["cpu", "gpu"],
        height=4,
        width=6,
        remove_legend=True,
        ymin=0,
        ymax=1200,
        remove_y=False,
    )

    mlrunner_times["env"] = [
        x.rsplit("-", 1)[0] for x in mlrunner_times.environment.values
    ]
    mlrunner_times["label"] = [
        re.sub("-(gpu|cpu)", "", x).replace("-", " ")
        for x in mlrunner_times.experiment.values
    ]
    mltimes = copy.deepcopy(mlrunner_times)
    mltimes = mltimes[
        mltimes.label.isin(
            ["state machine", "flux state machine", "state machine autoscale"]
        )
    ]
    me.make_plot(
        mltimes,
        title="MLRunner Times by Experiment",
        ydimension="duration",
        xdimension="env",
        outdir=img_outdir,
        ext="png",
        plotname="mlrunner_times_by_experiment",
        hue="label",
        palette=me.colors,
        plot_type="box",
        xlabel=None,
        ylabel="Duration (Seconds)",
        rotation=360,
        remove_x=True,
        order=["cpu", "gpu"],
        height=4,
        width=6,
        remove_legend=True,
        ymin=0,
        ymax=1200,
        remove_y=False,
    )

    # Create one plot for mlrunner and createsim for the paper
    # fig, axes = plt.subplots(1, 2, sharey=True, figsize=(10, 4))

    # For paper plot, we need to move legend outside to see the content
    fig = plt.figure(figsize=(12, 4))
    gs = plt.GridSpec(1, 3, width_ratios=[2, 2, 0.5])
    axes = []
    mlrunner_ax = fig.add_subplot(gs[0, 0])
    axes.append(mlrunner_ax)
    axes.append(fig.add_subplot(gs[0, 1], sharey=mlrunner_ax))
    axes.append(fig.add_subplot(gs[0, 2]))

    sns.set_style("whitegrid")
    sns.boxplot(
        mltimes,
        ax=axes[0],
        x="env",
        y="duration",
        hue="label",
        palette=me.colors,
        linewidth=1.8,
        whis=[5, 95],
        dodge=True,
    )
    axes[0].set_title("MLRunner Times by Experiment", fontsize=15)
    axes[0].set_ylabel("Duration (seconds)", fontsize=15)
    axes[0].set_xlabel("")

    sns.boxplot(
        createsim_times,
        ax=axes[1],
        x="env",
        y="duration",
        hue="label",
        palette=me.colors,
        linewidth=1.8,
        whis=[5, 95],
        dodge=True,
    )
    axes[1].set_title("Createsim Times by Experiment", fontsize=15)
    plt.ylim(0, 1200)
    plt.xticks(rotation=360)
    axes[1].set_ylabel("")
    axes[1].set_xlabel("")

    # Second plot has all colors
    handles, labels = axes[1].get_legend_handles_labels()
    axes[2].legend(
        handles, labels, loc="center left", bbox_to_anchor=(-0.5, 0.5), frameon=False
    )
    for ax in axes[0:2]:
        ax.get_legend().remove()
    axes[2].axis("off")

    plt.tight_layout()
    plt.savefig(os.path.join(img_outdir, "job_times_combined.svg"))
    plt.savefig(os.path.join(img_outdir, "job_times_combined.png"))
    plt.clf()


def count_outputs(indirs, outdir, completions=6):
    """
    Count number of outputs for analyses.
    """
    completed = combine_data_frames(indirs, "jobs-completed.csv")
    excess = combine_data_frames(indirs, "jobs-excess-completed.csv")
    img_outdir = os.path.join(outdir, "img")
    if not os.path.exists(img_outdir):
        os.makedirs(img_outdir)

    # Remove hyphen
    excess["experiment"] = [x.replace("-", " ") for x in excess.experiment.values]

    # Plot each.
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
        remove_x=True,
    )

    # For paper plot, we need to move legend outside to see the content
    fig = plt.figure(figsize=(8, 3))
    gs = plt.GridSpec(1, 2, width_ratios=[2, 0.5])
    axes = []
    axes.append(fig.add_subplot(gs[0, 0]))
    axes.append(fig.add_subplot(gs[0, 1]))

    # fig, axes = plt.subplots(1, 2, sharey=True, figsize=(18, 3.3))
    sns.set_style("whitegrid")
    sns.barplot(
        excess,
        ax=axes[0],
        x="job",
        y="count",
        hue="experiment",
    )
    axes[0].set_title("Excess Jobs by Experiment", fontsize=12)
    axes[0].set_ylabel("Excess Completed (count)", fontsize=12)
    axes[0].set_xlabel("")
    axes[0].set_yscale("log")

    handles, labels = axes[0].get_legend_handles_labels()
    axes[1].legend(
        handles, labels, loc="center left", bbox_to_anchor=(-0.1, 0.5), frameon=False
    )
    for ax in axes[0:1]:
        ax.get_legend().remove()
    axes[1].axis("off")

    plt.xticks(rotation=360)
    plt.tight_layout()
    plt.savefig(os.path.join(img_outdir, "excess-jobs-paper-plot.svg"))
    plt.clf()

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


def parse_pulling_times(indirs, outdir):
    """
    Read events and turn into data frame with container pull times
    """
    mummi_pulling = pandas.read_csv(
        os.path.join(indirs[0], "container-pulling-times.csv"), index_col=0
    )
    sm_pulling = pandas.read_csv(
        os.path.join(indirs[1], "container-pulling-times.csv"), index_col=0
    )
    sm_flux_pulling = pandas.read_csv(
        os.path.join(indirs[2], "container-pull-times.csv"), index_col=0
    )
    # Now add singularity (flux)
    sm_flux_pulling["name"] = None
    sm_flux_pulling.loc[:, "experiment"] = [
        f"state-machine-flux-{x}" for x in sm_flux_pulling.experiment.values
    ]
    mummi_pulling.loc[:, "experiment"] = [
        f"mummi-{x}" for x in mummi_pulling.experiment.values
    ]
    sm_pulling.loc[:, "experiment"] = [
        f"state-machine-{x}" for x in sm_pulling.experiment.values
    ]
    df = pandas.concat([mummi_pulling, sm_pulling, sm_flux_pulling])
    df.to_csv(os.path.join(outdir, "all-container-pull-times.csv"))
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
        "on-premises": read_json(
            os.path.join(indirs[3], "workflow-endpoint-times.json")
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
    cost_per_hour = []
    # Lassen cost is 0.0158 per core hour. So for 44 cores per node, 0.6952/hour.
    for x in times.environment:
        if "on-premises" in x:
            cost_per_hour.append(0.6952)
        # hpc7g
        elif "cpu" in x:
            cost_per_hour.append(1.683)
        # px.2xlarge
        else:
            cost_per_hour.append(3.06)
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
            if "on-premises" in experiment:
                total_costs[experiment][iteration] = (sum(uptimes) / 60 / 60) * 0.6952
            elif "cpu" in experiment:
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
    cost_df["labels"] = derive_pretty_labels(cost_df.operator.values)
    me.make_plot(
        cost_df,
        title="Total Cost to Run Workflow",
        ydimension="cost",
        xdimension="labels",
        outdir=os.path.join(outdir, "img"),
        ext="png",
        plotname="workflow_total_cost_onpremises",
        hue="environment",
        hue_order=["gpu", "cpu"],
        plot_type="bar",
        order=[
            "flux\n state machine",
            "state machine \nautoscale",
            "state machine",
            "mummi",
            "on premises",
        ],
        xlabel=None,
        ylabel="Cost ($)",
        rotation=360,
        width=8,
        height=4,
    )
    print(cost_df.groupby(["environment", "labels"]).cost.mean())

    # And without on premises
    me.make_plot(
        cost_df,
        title="Total Cost to Run Workflow",
        ydimension="cost",
        xdimension="labels",
        outdir=os.path.join(outdir, "img"),
        ext="png",
        plotname="workflow_total_cost",
        hue="environment",
        hue_order=["gpu", "cpu"],
        plot_type="bar",
        order=[
            "flux\n state machine",
            "state machine \nautoscale",
            "state machine",
            "mummi",
        ],
        xlabel=None,
        ylabel="Cost ($)",
        rotation=360,
        width=8,
        height=4,
    )


if __name__ == "__main__":
    main()
