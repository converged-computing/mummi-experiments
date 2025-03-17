#!/usr/bin/env python3

import argparse
import os
import sys

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
            "cpu-arm-no-autoscaling",
            "cpu-arm-no-autoscaling-0",
            "cpu-arm-no-autoscaling-1",
        ],
        "cpu-autoscale": [
            "cpu-arm-autoscale",
            "cpu-arm-autoscale-0",
            "cpu-arm-autoscale-1",
        ],
        "gpu-static": [
            "gpu-no-autoscaling",
            "gpu-no-autoscaling-0",
            "gpu-no-autoscaling-1",
        ],
        "gpu-autoscale": ["gpu-autoscale", "gpu-autoscale-0", "gpu-autoscale-1"],
    }
    indirs, event_files = me.collect_inputs(_indirs, indir)

    # Parse times for pulling containers (also returns nodes)
    times_df, _ = me.parse_events(outdir, event_files)
    me.plot_pulling_times(times_df, outdir)

    # Now let's count outputs (total and excess)
    me.count_outputs(indirs, outdir, completions=args.completions)

    # Now let's look at times for jobs
    me.job_timings(indirs, outdir)

    # Now look at times for the workflow manager
    manager_df, workflow_starts, workflow_ends = me.workflow_manager(indirs, outdir)
    me.calculate_costs(
        indirs, times_df, manager_df, workflow_starts, workflow_ends, outdir
    )


if __name__ == "__main__":
    main()
