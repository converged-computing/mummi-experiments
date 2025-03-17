#!/usr/bin/env python3

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
    me.calculate_costs_static(
        indirs, manager_df, workflow_starts, workflow_ends, outdir
    )


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
