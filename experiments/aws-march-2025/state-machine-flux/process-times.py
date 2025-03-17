#!/usr/bin/env python3

import json
import argparse
import os
import sys
import pandas

here = os.path.abspath(os.path.dirname(__file__))
root = os.path.dirname(here)
sys.path.insert(0, root)
import mummi_experiments as me


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
    indirs = {
        "cpu-static": [
            os.path.join(indir, "cpu", x)
            for x in os.listdir(os.path.join(indir, "cpu"))
            if "error" not in x
        ],
        "gpu-static": [
            os.path.join(indir, "gpu", x)
            for x in os.listdir(os.path.join(indir, "gpu"))
            if "error" not in x
        ],
    }

    # Container pulling was done separately
    times_df = parse_container_pulls(indir, outdir)
    me.plot_pulling_times(times_df, outdir)

    # Now let's count outputs (total and excess)
    me.count_outputs(indirs, outdir, completions=args.completions, has_data_dir=False)

    # Now let's look at times for jobs
    me.job_timings(indirs, outdir, has_data_dir=False)

    # Now look at times for the workflow manager
    manager_df, workflow_starts, workflow_ends = me.workflow_manager(indirs, outdir)

    # Note that we add the pulling times here because they were not included in the experiment
    # and need to be.
    manager_df = add_pulling_times(manager_df, times_df, outdir)
    
    # Finally, add running times
    add_job_running_times(times_df, outdir)
    me.calculate_costs_static(
        indirs, manager_df, workflow_starts, workflow_ends, outdir
    )

def add_job_running_times(df, outdir):
    """
    Add job running times from flux output files
    """
    # Finally, we got the running events from Kubernetes, and need to add them here.
    idx = df.shape[0] + 1
    job_times = parse_job_times()
    me.write_json(job_times, os.path.join(outdir, "job-times.json"))
    for experiment, job_names in job_times.items():
        for job_name, iterations in job_names.items():
            for iteration, timelist in iterations.items():
                for runtime in timelist:
                    df.loc[idx, :] = [
                        None,
                        job_name,
                        "running",
                        runtime,
                        None,
                        f"{experiment}-static",
                        iteration,
                    ]
                    idx += 1

    df.to_csv(os.path.join(outdir, "container-pull-times.csv"))
    

def add_pulling_times(manager_df, times_df, outdir):
    """
    All kubernetes experiments include the time to pull the mlrunner, createsim, and cganalysis to each
    node, so we have to add that here.
    """
    # Here is subset without pull
    subset = manager_df[manager_df["global"] == "workflow_complete"]
    subset["global"] = subset["global"].replace(
        {"workflow_complete": "workflow_complete_without_pulling"}
    )

    # We will assume the pulls happened in parallel and once per node (just count cost once)
    additional_time = {}
    for experiment in subset.experiment.unique():
        additional_time[experiment] = {}
        for iteration in subset.iteration.unique():
            times_df[times_df.experiment == experiment]
            experiment_df = times_df[times_df.experiment == experiment]
            experiment_df = experiment_df[experiment_df.iteration == iteration]
            # One for each of mlrunner, createsim, cganalysis
            assert experiment_df.shape[0] == 3
            additional_time[experiment][iteration] = experiment_df.duration.sum()

    # Create an updated data frame
    updated = manager_df[manager_df["global"] != "workflow_complete"]
    updated = pandas.concat([updated, subset])
    idx = updated.shape[0] + 1
    for experiment, additions in additional_time.items():
        for iteration, addition in additions.items():
            time_without_pull = subset[
                (subset.experiment == experiment) & (subset.iteration == iteration)
            ].duration.values[0]
            updated.loc[idx, :] = [
                experiment,
                "workflow_start",
                time_without_pull + addition,
                "workflow_complete",
                iteration,
            ]
            idx += 1
    updated.to_csv(os.path.join(outdir, "workflow-individual-times.csv"))
    return updated


def parse_job_times():
    """
    This is akin to what the Kubernetes event exporter gives us.
    """
    times = {"cpu": {}, "gpu": {}}
    gpu = [
        x
        for x in me.find_inputs(os.path.join(here, "results", "gpu"), "out")
        if "error" not in x
    ]
    cpu = [
        x
        for x in me.find_inputs(os.path.join(here, "results", "cpu"), "out")
        if "error" not in x
    ]
    for filename in cpu + gpu:
        if not filename.endswith(".out"):
            continue
        content = me.read_file(filename)
        # Get the two wrapping timestamps
        run_start = json.loads(
            [x for x in content.split("\n") if "shell.start" in x][0]
        )["timestamp"]
        run_end = json.loads(
            [x for x in content.split("\n") if "shell.task-exit" in x][0]
        )["timestamp"]
        environ = "cpu" if "cpu" in filename else "gpu"
        job_name = os.path.basename(filename).split("-")[1]
        if job_name not in times[environ]:
            times[environ][job_name] = {}
        iteration = int(
            [x for x in filename.split(os.sep) if "iter" in x][0].split("-")[-1]
        )
        if iteration not in times[environ][job_name]:
            times[environ][job_name][iteration] = []
        times[environ][job_name][iteration].append(run_end - run_start)
    return times


def parse_container_pulls(indir, outdir):
    """
    Since it takes upwards of 20 minutes to make a Singularity container, we pre-pulled
    to the VMs. And then did a separate pulling study to do 3 iterations of each pull,
    just to one node. These times would need to be multiplied across nodes.
    """
    # Yes, I had a typo "createsime" :)
    tag_lookup = {
        "cpu": {
            "mlrunner": "mlrunner-arm-singularity",
            "cganalysis": "cganalysis-arm",
            "createsime": "createsims-arm",
        },
        "gpu": {
            "mlrunner": "mlrunner-gpu",
            "cganalysis": "cganalysis-gpu",
            "createsime": "createsims-gpu",
        },
    }

    pulls_dir = os.path.join(indir, "container-pulls")
    df = pandas.DataFrame(
        columns=[
            "kind",
            "job",
            "event",
            "duration",
            "container",
            "experiment",
            "iteration",
        ]
    )
    idx = 0
    container = "docker://633731392008.dkr.ecr.us-east-1.amazonaws.com/mini-mummi"
    for environ in ["gpu", "cpu"]:
        pull_texts = me.find_inputs(os.path.join(pulls_dir, environ), "txt")
        for pull_text in pull_texts:
            job = os.path.basename(pull_text).split("-")[0]
            iteration = int(pull_text.replace(".txt", "").split("-")[-1])
            content = me.read_file(pull_text)
            seconds = me.parse_time_pulled(
                [x for x in content.split("\n") if "real" in x][0].split("\t")[-1]
            )
            tag = tag_lookup[environ][job]
            container_name = f"{container}:{tag}"
            df.loc[idx, :] = [
                "singularity",
                job,
                "pulled",
                seconds,
                container_name,
                f"{environ}-static",
                iteration,
            ]
            idx += 1

    df.to_csv(os.path.join(outdir, "container-pull-times.csv"))
    return df


if __name__ == "__main__":
    main()
