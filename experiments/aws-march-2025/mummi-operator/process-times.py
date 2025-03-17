#!/usr/bin/env python3

import argparse
import json
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
    if not os.path.exists(outdir):
        os.makedirs(outdir)

    # Specific cpu and gpu results
    _indirs = {
        "cpu-static": [
            #            "cpu-static-0",
            #            "cpu-static-1",
            #            "cpu-static-2",
        ],
        "gpu-static": [
            "gpu-static-0",
            "gpu-static-1",
            "gpu-static-2",
        ],
    }
    indirs, event_files = me.collect_inputs(_indirs, indir)
    times_df, _ = me.parse_events(outdir, event_files)
    me.plot_pulling_times(times_df, outdir)

    # Now let's count outputs (total and excess)
    # the Mummi operator has slightly different ways to save output
    # We read from tarfile into memory for subsequent analyses
    me.count_outputs(
        indirs,
        outdir,
        completions=args.completions,
        mlrunner_tag="latest",
        createsims_pattern="createsims-output.tar.gz",
        cganalysis_pattern="cganalysis-output.tar.gz",
    )

    # Now let's look at times for jobs
    job_timings(indirs, outdir)

    # Now look at times for the workflow manager
    workflow_manager(indirs, outdir)


def workflow_manager(indirs, outdir):
    """
    Look at timings for the workflow manager. Mummi has to be done differently
    because the manager exits (and prints at the end) so we use the last timestamp.
    """
    workflow_starts = {}
    workflow_ends = {}
    df = pandas.DataFrame(columns=["experiment", "event", "duration", "global", "iteration"])
    idx = 0
    for experiment, indirset in indirs.items():
        for _indir in indirset:
            iteration = me.get_experiment_iteration(_indir)
            times = me.read_json(os.path.join(_indir, "workflow-times.json"))
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
                if complete_ts not in times["timestamps"]:

                    # This method doesn't have a good way to determine the end, so we use the last event
                    if event == "wfmanager_run_workflow":
                        ending_ts = list(times["timestamps"].values())[-1]
                        workflow_starts[experiment][iteration] = timestamp
                        workflow_ends[experiment][iteration] = ending_ts
                        duration = ending_ts - timestamp
                        df.loc[idx, :] = [experiment, event, duration, global_event, iteration]
                        idx += 1
                        continue

                    print(f"Warning: missing completion marker for {event}")
                    continue
                duration = times["timestamps"][complete_ts] - timestamp
                df.loc[idx, :] = [experiment, event, duration, global_event, iteration]
                idx += 1

    # Calculate sum totals for events. E.g., some functions are run multiple times
    # Note that this is across samples
    function_times = df.groupby(["experiment", "global", "iteration"])["duration"].sum()
    print(function_times)
    function_times = function_times.to_frame()

    # Make a more parseable data frame
    func_df = pandas.DataFrame(columns=["experiment", "function", "duration", "iteration"])
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

    # The only meaningful comparison is the workflow running time to get 6 samples
    print("See workflow running time to get 6 samples")
    print(subset.groupby(["experiment", "global"]).duration.mean())
    return df


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
    for experiment, indirset in indirs.items():
        for _indir in indirset:
            data_dir = os.path.join(_indir, "data")
            iteration = me.get_experiment_iteration(_indir)

            # This is the total number of samples that were pushed from mlserver
            samples = [
                x
                for x in me.find_inputs(data_dir, "createsims-output.tar.gz")
                if "/createsim/" in x
            ]

            # Now we read in results via tarfile (only done for MuMMI)
            df, idx = parse_createsim_times(df, samples, experiment, idx, iteration)
            samples = [
                x
                for x in me.find_inputs(data_dir, "cganalysis-output.tar.gz")
                if "/cganalysis/" in x
            ]
            df, idx = parse_cganalysis_times(df, samples, experiment, idx, iteration)

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

    # Save individual times too
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
        files = me.read_tarfile(sample)
        assert "tmp/out/createsims_success" in files
        times = json.loads(files["tmp/out/createsims-times.json"])
        sample_name = sample.split(os.sep)[-3]
        df, idx = me.parse_single_time_event(
            df,
            idx,
            times,
            experiment,
            iteration,
            sample_name,
            "createsim",
            multiple_runs=multiple_runs,
        )

    return df, idx


def parse_cganalysis_times(df, samples, experiment, idx=0, iteration=0):
    """
    Parse timing output from cganalysis
    """
    for sample in samples:
        files = me.read_tarfile(sample)
        times = json.loads(files["tmp/out/cganalysis-times.json"])
        sample_name = sample.split(os.sep)[-3]
        df, idx = me.parse_single_time_event(
            df,
            idx,
            times,
            experiment,
            iteration,
            sample_name,
            "cganalysis",
        )
    return df, idx


if __name__ == "__main__":
    main()
