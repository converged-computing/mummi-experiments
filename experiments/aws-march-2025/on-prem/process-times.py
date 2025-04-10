#!/usr/bin/env python3

from datetime import datetime
import argparse
import json
import os
import sys
import re

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
    img_outdir = os.path.join(outdir, "img")
    if not os.path.exists(img_outdir):
        os.makedirs(img_outdir)

    # Note that on premises is only GPU
    indirs = [
        os.path.join(here, "gpu", "iter-1"),
        os.path.join(here, "gpu", "iter-2"),
        os.path.join(here, "gpu", "iter-3"),
    ]

    # Count outputs for each
    final_cgs = count_outputs(indirs, outdir, args.completions)

    # Now let's look at times for jobs
    end_times = job_timings(indirs, outdir, final_cgs)

    # Now look at times for the workflow manager
    workflow_manager(indirs, end_times, outdir)


def get_final_cganalysis(indir):
    manager_out = me.read_file(me.find_inputs(indir, "wfmanager[.]log")[0])
    samples = [x for x in manager_out.split("\n") if "We have computed [" in x][-1]
    return json.loads(
        ("[" + re.split("([[]|[]])", samples)[-3] + "]").replace("'", '"')
    )


def get_experiment_iteration(indir):
    """
    We will count starting at 0 (the repo starts at 1)
    """
    dirname = os.path.basename(indir)
    dirname = dirname.replace("iter-", "")
    return int(dirname) - 1


def count_outputs(
    indirs,
    outdir,
    completions=10,
):
    """
    Count number of outputs for analyses.
    """
    # Note that excess here only includes completions, we don't account for
    # jobs that started running and didn't save output (partial run or otherwise)
    df = pandas.DataFrame(columns=["experiment", "job", "count", "iteration"])
    excess = pandas.DataFrame(columns=["experiment", "job", "count", "iteration"])
    idx = 0

    # Keep track of final cganalysis sets for each run
    final_cg = {}

    # Experiment is always gpu-static
    experiment = "gpu-static"
    for indir in indirs:
        iteration = get_experiment_iteration(indir)

        # The manager file will show valid samples generated
        mlserver_out = me.read_file(me.find_inputs(indir, "mlserver")[0])

        valid_files = []
        for valid_listing in [
            x.split("=", 1)[-1] for x in mlserver_out.split("\n") if "valid_files" in x
        ]:
            valid_files += json.loads(valid_listing.replace("'", '"'))
        valid_files = set(valid_files)
        df.loc[idx, :] = [experiment, "mlsample", len(valid_files), iteration]
        excess.loc[idx, :] = [
            experiment,
            "mlsample",
            len(valid_files) - completions,
            iteration,
        ]
        idx += 1
        createsims = me.find_inputs(indir, "createsims.out")
        df.loc[idx, :] = [experiment, "createsim", len(createsims), iteration]
        excess.loc[idx, :] = [
            experiment,
            "createsim",
            len(createsims) - completions,
            iteration,
        ]
        idx += 1
        cganalysis = me.find_inputs(indir, "cg_analysis.out")

        # These are those that were finished
        final_cgs = get_final_cganalysis(indir)
        final_cg[indir] = final_cgs
        cganalysis = [
            x for x in cganalysis if os.path.basename(os.path.dirname(x)) in final_cgs
        ]
        df.loc[idx, :] = [experiment, "cganalysis", len(cganalysis), iteration]

        # These are the ones that were finished in the time
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
    # Return the final set of cganalysis we used (so we don't need to parse again)
    return final_cg


def workflow_manager(indirs, job_end_times, outdir):
    """
    Look at timings for the workflow manager.
    """
    workflow_starts = {}
    workflow_ends = {}
    df = pandas.DataFrame(
        columns=["experiment", "event", "duration", "global", "iteration"]
    )
    idx = 0
    experiment = "gpu-static"
    for indir in indirs:
        iteration = get_experiment_iteration(indir)
        times = me.read_json(os.path.join(indir, "wfmanager-times.json"))
        if experiment not in workflow_starts:
            workflow_starts[experiment] = {}
            workflow_ends[experiment] = {}
        if iteration not in workflow_starts[experiment]:
            workflow_starts[experiment][iteration] = {}
            workflow_ends[experiment][iteration] = {}
        for name, timestamp in times["timestamps"].items():
            if "_start" not in name:
                continue
            event = name.replace("_start", "")

            # We will sum these totals at the end.
            global_event = event.rsplit("_", 1)[0]
            suffix = event.split("_")[-1]
            try:
                int(suffix)
            except:
                global_event = event

            complete_ts = f"{event}_complete"
            if event == "wfmanager_setup":
                ending_ts = times["timestamps"]["wfmanager_stopped_workflow"]
                workflow_starts[experiment][iteration] = timestamp
                workflow_ends[experiment][iteration] = ending_ts
                duration = ending_ts - timestamp
                df.loc[idx, :] = [
                    experiment,
                    "workflow_complete",
                    duration,
                    "wfmanager_run_workflow",
                    iteration,
                ]
                idx += 1
                print(duration)
            elif complete_ts not in times["timestamps"]:
                print(f"Warning: missing completion marker for {event}")
                continue
            else:
                duration = times["timestamps"][complete_ts] - timestamp
                # These are the other tail of workflow setup
                if duration < 1:
                    continue
                df.loc[idx, :] = [experiment, event, duration, global_event, iteration]
                idx += 1

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

    # Save workflow starts and ends
    me.write_json(
        {"starts": workflow_starts, "ends": workflow_ends},
        os.path.join(outdir, "workflow-endpoint-times.json"),
    )

    # Remove functions that total sum across the workflow is < 1 second
    less_than_one_second = func_df[func_df.duration < 1].function.tolist()
    subset = df[~df["global"].isin(less_than_one_second)]
    me.make_plot(
        subset,
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

    # The only meaningful comparison is the workflow running time to get all completions
    print("See workflow running time to get 10 samples")
    print(subset.groupby(["experiment", "global"]).duration.mean())
    return df


def job_timings(indirs, outdir, final_cgs):
    """
    Find output files for job timings.
    """
    # We need to save end times for last cganalysis for one erroneous wfmanager run
    end_times = {}

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

    experiment = "gpu-static"
    end_times[experiment] = {}
    for indir in indirs:
        iteration = get_experiment_iteration(indir)
        if iteration not in end_times[experiment]:
            end_times[experiment][iteration] = {"cganalysis_run_complete": []}

        # The manager file will show valid samples generated
        mlserver_out = me.read_file(me.find_inputs(indir, "mlserver")[0])

        # This is the total number of samples that were pushed from mlserver
        samples = me.find_inputs(indir, "createsims-times.json")
        df, idx = me.parse_createsim_times(df, samples, experiment, idx, iteration)
        samples = me.find_inputs(indir, "cganalysis-times.json")

        # Only use those that are in the completed window
        samples = [
            x
            for x in samples
            if os.path.basename(os.path.dirname(x)) in final_cgs[indir]
        ]
        df, end_times, idx = parse_cganalysis_times(
            df, end_times, samples, experiment, idx, iteration
        )

    # Calculate sum totals for events. E.g., some functions are run multiple times
    # Note that this is across samples
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
    df.to_csv(os.path.join(outdir, "function-individual-times.csv"))

    me.make_plot(
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
    return end_times

def parse_ts(timestamp):
    fmt = "%Y-%m-%d %H:%M:%S,%f"
    return datetime.strptime(timestamp, fmt)

def parse_cganalysis_times(df, end_times, samples, experiment, idx=0, iteration=0):
    """
    Parse timing output from cganalysis
    
    This was problematic that the on-prem runs don't have the final timestamps. We know
    it was set to end at 30 minutes, so the best we can do is add 30 minutes to that.
    """
    for sample in samples:
        times = json.loads(me.read_file(sample))
        sample_name = sample.split(os.sep)[-3]
        # For the ending time, the on prem run didn't have the stopping time. But we have full logs! We will calculate it
        # from there.
        cganalysis_log = me.read_file(os.path.join(os.path.dirname(sample), "cg_analysis.out"))
        ts_start = [x for x in cganalysis_log.split('\n') if x][0].split(' - ')[0]
        ts_end = [x for x in cganalysis_log.split('\n') if x][-1].split(' - ')[0]
        cganalysis_runtime = parse_ts(ts_end) - parse_ts(ts_start)
        print(times["timestamps"])
        end_times[experiment][iteration]["cganalysis_run_complete"].append(parse_ts(ts_end).timestamp())
        times["timestamps"]["cganalysis_run_start"] = parse_ts(ts_start).timestamp()
        times["timestamps"]["cganalysis_run_complete"] = parse_ts(ts_end).timestamp()
        df, idx = me.parse_single_time_event(
            df,
            idx,
            times,
            experiment,
            iteration,
            sample_name,
            "cganalysis",
        )
    return df, end_times, idx


if __name__ == "__main__":
    main()
