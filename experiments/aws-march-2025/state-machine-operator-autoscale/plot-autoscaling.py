#!/usr/bin/env python3

import argparse
import json
import os
import re

here = os.path.abspath(os.path.dirname(__file__))
root = os.path.dirname(here)

from state_machine_operator.analysis.manager import (
    WorkflowTimesParser,
    NodesTimesParser,
)

timestamp_format = "%Y-%m-%dT%H:%M:%SZ"


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


def find_inputs(input_dir, pattern="*.out"):
    """
    Find inputs (cganalysis output files)
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
    if not os.path.exists(outdir):
        os.makedirs(outdir)

    img_outdir = os.path.join(outdir, "img")
    if not os.path.exists(img_outdir):
        os.makedirs(img_outdir)

    wftimes_gpu = [
        [2, "static", "monitor/gpu-no-autoscaling-1/workflow-times.json"],
        [2, "autoscale", "monitor/gpu-autoscale-1/workflow-times.json"],
        [0, "autoscale", "monitor/gpu-autoscale/workflow-times.json"],
        [0, "static", "monitor/gpu-no-autoscaling/workflow-times.json"],
        [1, "autoscale", "monitor/gpu-autoscale-0/workflow-times.json"],
        [1, "static", "monitor/gpu-no-autoscaling-0/workflow-times.json"],
    ]

    wftimes_cpu = [
        [1, "autoscale", "monitor/cpu-arm-autoscale-0/workflow-times.json"],
        [1, "static", "monitor/cpu-arm-no-autoscaling-0/workflow-times.json"],
        [0, "static", "monitor/cpu-arm-no-autoscaling/workflow-times.json"],
        [2, "autoscale", "monitor/cpu-arm-autoscale-1/workflow-times.json"],
        [0, "autoscale", "monitor/cpu-arm-autoscale/workflow-times.json"],
        [2, "static", "monitor/cpu-arm-no-autoscaling-1/workflow-times.json"],
    ]

    # Be pedantic
    gpu_files = [
        [2, "static", "monitor/gpu-no-autoscaling-1/cluster-nodes.json"],
        [2, "autoscale", "monitor/gpu-autoscale-1/cluster-nodes.json"],
        [0, "autoscale", "monitor/gpu-autoscale/cluster-nodes.json"],
        [0, "static", "monitor/gpu-no-autoscaling/cluster-nodes.json"],
        [1, "autoscale", "monitor/gpu-autoscale-0/cluster-nodes.json"],
        [1, "static", "monitor/gpu-no-autoscaling-0/cluster-nodes.json"],
    ]

    cpu_files = [
        [1, "static", "monitor/cpu-arm-no-autoscaling-0/cluster-nodes.json"],
        [1, "autoscale", "monitor/cpu-arm-autoscale-0/cluster-nodes.json"],
        [0, "static", "monitor/cpu-arm-no-autoscaling/cluster-nodes.json"],
        [2, "autoscale", "monitor/cpu-arm-autoscale-1/cluster-nodes.json"],
        [0, "autoscale", "monitor/cpu-arm-autoscale/cluster-nodes.json"],
        [2, "static", "monitor/cpu-arm-no-autoscaling-1/cluster-nodes.json"],
    ]

    # GPU: Parse workflow times
    parser = WorkflowTimesParser()
    for fileset in wftimes_gpu:
        iteration, experiment, filename = fileset
        parser.add_experiment(filename, experiment, iteration)

    img_outdir = os.path.join(outdir, "img")
    if not os.path.exists(img_outdir):
        os.makedirs(img_outdir)

    # Parse node timings - first gpu
    node_parser = NodesTimesParser(node_filter=["p3.2xlarge"])
    for fileset in gpu_files:
        iteration, experiment, filename = fileset
        node_parser.add_nodes(
            filename,
            experiment=experiment,
            iteration=iteration,
            workflow_start=parser.workflow_starts[experiment][iteration],
            workflow_end=parser.workflow_ends[experiment][iteration],
        )

    # Colors for autoscaling / static - y and b are good too
    colors = {"static": "c", "autoscale": "m"}

    # Make a gantt chart of nodes
    title = "Node Uptimes for Static vs Autoscaling (GPU)"
    for extension in ['png', 'svg']:
        node_parser.to_gantt(
            os.path.join(outdir, f"node-gantt-chart-gpu.{extension}"), title=title, colors=colors
        )

    # CPU: Parse workflow times
    parser = WorkflowTimesParser()
    for fileset in wftimes_cpu:
        iteration, experiment, filename = fileset
        parser.add_experiment(filename, experiment, iteration)

    print(parser.df)

    # Parse node timings - first gpu
    node_parser = NodesTimesParser(node_filter=["hpc7g.16xlarge"])
    for fileset in cpu_files:
        iteration, experiment, filename = fileset
        node_parser.add_nodes(
            filename,
            experiment=experiment,
            iteration=iteration,
            workflow_start=parser.workflow_starts[experiment][iteration],
            workflow_end=parser.workflow_ends[experiment][iteration],
        )

    # Make a gantt chart of nodes
    title = "Node Uptimes for Static vs Autoscaling (CPU)"
    for extension in ['png', 'svg']:
        node_parser.to_gantt(
            os.path.join(outdir, f"node-gantt-chart-cpu.{extension}"), title=title, colors=colors
        )
    
if __name__ == "__main__":
    main()
