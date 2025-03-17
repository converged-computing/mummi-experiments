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

    # No container pulling here
    # Now let's count outputs (total and excess)
    me.count_outputs(indirs, outdir, completions=args.completions, has_data_dir=False)

    # Now let's look at times for jobs
    me.job_timings(indirs, outdir, has_data_dir=False)

    # Now look at times for the workflow manager
    manager_df, workflow_starts, workflow_ends = me.workflow_manager(indirs, outdir)
    me.calculate_costs_static(
        indirs, manager_df, workflow_starts, workflow_ends, outdir
    )


if __name__ == "__main__":
    main()
