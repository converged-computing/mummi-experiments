#!/usr/bin/env python3

import argparse
import json
import os
import re
import sys
import tarfile
import io

from datetime import datetime

import matplotlib.pylab as plt
import pandas
import seaborn as sns

here = os.path.abspath(os.path.dirname(__file__))
root = os.path.dirname(here)

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
    indir = os.path.abspath(args.root)
    if not os.path.exists(outdir):
        os.makedirs(outdir)

    # Specific cpu and gpu results
    cpu_indir = os.path.join(indir, "cpu-static-1")
    gpu_indir = os.path.join(indir, "gpu-static-1")

    # Parse times for pulling containers
    gpu_pulling_files = find_inputs(gpu_indir, "events-")
    cpu_pulling_files = find_inputs(cpu_indir, "events-")
    pulling_files = gpu_pulling_files + cpu_pulling_files
    times = parse_pulling_data(outdir, pulling_files)
    times_df = parse_pulling_times(times)
    # This returns the start of a summary df we can add costs to
    summary_df = plot_pulling_times(times_df, outdir)
    
    # Now let's count outputs (total and excess)
    count_outputs([cpu_indir, gpu_indir], outdir, completions=args.completions)

    # Now let's look at times for jobs
    job_timings([cpu_indir, gpu_indir], outdir)
    
    # Now look at times for the workflow manager
    workflow_manager([cpu_indir, gpu_indir], outdir)
    
    # TODO calculate costs, likely when we add autoscaling

def workflow_manager(indirs, outdir):
    """
    Look at timings for the workflow manager
    """
    df = pandas.DataFrame(columns=['experiment', 'event', 'duration', 'global'])
    idx = 0
    for _indir in indirs:
        experiment = "gpu-static" if "gpu-static" in _indir else "cpu-static"
        times = read_json(os.path.join(_indir, "wfmanager-times.json"))
        for name, timestamp in times['timestamps'].items():
            if "_start" not in name:
                continue
            event = name.replace('_start', '')
            
            # We will sum these totals at the end.
            global_event = event.rsplit('_', 1)[0]
            suffix = event.split('_')[-1]
            try:
                int(suffix)
            except:
                global_event = event
                
            complete_ts = f"{event}_complete"
            if complete_ts not in times["timestamps"]:
                # This method doesn't have a good way to determine the end, so we use the last event
                if event == "wfmanager_run_workflow":
                    ending_ts =  list(times['timestamps'].values())[-1]
                    duration = ending_ts - timestamp
                    df.loc[idx, :] = [experiment, event, duration, global_event]
                    idx +=1 
                    continue
                    
                print(f"Warning: missing completion marker for {event}")
                continue
            duration = times["timestamps"][complete_ts] - timestamp
            df.loc[idx, :] = [experiment, event, duration, global_event]
            idx += 1

    # Calculate sum totals for events. E.g., some functions are run multiple times
    # Note that this is across samples
    function_times = df.groupby(['experiment', 'global'])['duration'].sum()
    print(function_times)
    function_times = function_times.to_frame()
    
    # Make a more parseable data frame
    func_df = pandas.DataFrame(columns=['experiment', 'function', 'duration'])
    idx = 0
    for row in function_times.iterrows():
        func_df.loc[idx, :] = [row[0][0], row[0][1], row[1].duration]
        idx +=1
    func_df.to_csv(os.path.join(outdir, "workflow-summed-times.csv"))

    # Save individual times too
    df.to_csv(os.path.join(outdir, "workflow-individual-times.csv"))

    # Remove functions that total sum across the workflow is < 1 second
    less_than_one_second = func_df[func_df.duration < 1].function.tolist()
    subset = df[~df['global'].isin(less_than_one_second)]
    make_plot(
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
        height=12
    )
    
    # The only meaningful comparison is the workflow running time to get 6 samples
    print("See workflow running time to get 6 samples")
    print(subset.groupby(['experiment', 'global']).duration.mean())


def job_timings(indirs, outdir):
    """
    Find output files for job timings.
    """
    # global is the function in absence of an iteration identifier
    df = pandas.DataFrame(columns=['experiment', 'job', 'sample', 'event', 'duration', 'global'])
    idx = 0
    for _indir in indirs:
        experiment = "gpu-static" if "gpu-static" in _indir else "cpu-static"
        data_dir = os.path.join(_indir, "data")
        
        # This is the total number of samples that were pushed from mlserver
        samples = [x for x in find_inputs(data_dir, "createsims-output.tar.gz") if "/createsim/" in x]
        
        # Now we read in results via tarfile
        df, idx = parse_createsim_times(df, samples, experiment, idx)

        samples = [x for x in find_inputs(data_dir, "cganalysis-output.tar.gz") if "/cganalysis/" in x]
        df, idx = parse_cganalysis_times(df, samples, experiment, idx)

    # Calculate sum totals for events. E.g., some functions are run multiple times
    # Note that this is across samples
    function_times = df.groupby(['experiment', 'global', 'job'])['duration'].sum()
    print(function_times)
    function_times = function_times.to_frame()
    
    # Make a more parseable data frame
    func_df = pandas.DataFrame(columns=['experiment', 'function', 'job', 'duration'])
    idx = 0
    for row in function_times.iterrows():
        func_df.loc[idx, :] = [row[0][0], row[0][1], row[0][2], row[1].duration]
        idx +=1
    func_df.to_csv(os.path.join(outdir, "function-summed-times.csv"))

    # Save individual times too
    df.to_csv(os.path.join(outdir, "function-individual-times.csv"))

    make_plot(
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
        height=12
    )


def parse_createsim_times(df, samples, experiment, idx=0):
    """
    Parse timing output from createsims
    """
    # These are functions that can be run more than once, and have an iteration id at the end
    multiple_runs = ["createsims_gromacs_energy_minimization", "createsims_gromacs_make_ndx", 
                     "createsims_generate_velocities", 'createsims_short_equilibration',
                     'createsims_pull_molecules', 'createsims_mdrun_lipids_water',
                     'createsims_trjconv_lipids_water']
        
    for sample in samples:
        files = read_tarfile(sample)
        assert 'tmp/out/createsims_success' in files
        times = json.loads(files['tmp/out/createsims-times.json'])
        sample_name = sample.split(os.sep)[-3]

        # Save all total durations
        for name, duration in times["times"].items():
            df.loc[idx, :] = [experiment, "createsim", sample_name, name, duration, name]
            idx += 1
            
        # For all timestamps, calculate start to complete
        for name, timestamp in times['timestamps'].items():
            if "_start" not in name:
                continue
            event = name.replace('_start', '')
            
            # We will sum these totals at the end.
            global_event = event.rsplit('_', 1)[0]
            if global_event not in multiple_runs:
                global_event = event
                
            complete_ts = f"{event}_complete"
            if complete_ts not in times["timestamps"]:
                print(f"Warning: missing completion marker for {event}")
                continue
            duration = times["timestamps"][complete_ts] - timestamp
            df.loc[idx, :] = [experiment, "createsim", sample_name, event, duration, global_event]
            idx += 1
    return df, idx


def parse_cganalysis_times(df, samples, experiment, idx=0):
    """
    Parse timing output from cganalysis
    """        
    for sample in samples:
        files = read_tarfile(sample)
        times = json.loads(files['tmp/out/cganalysis-times.json'])
        sample_name = sample.split(os.sep)[-3]

        # Save all total durations
        for name, duration in times["times"].items():
            df.loc[idx, :] = [experiment, "cganalysis", sample_name, name, duration, name]
            idx += 1
            
        # For all timestamps, calculate start to complete
        for name, timestamp in times['timestamps'].items():
            if "_start" not in name:
                continue
            event = name.replace('_start', '')
            complete_ts = f"{event}_complete"
            if complete_ts not in times["timestamps"]:
                print(f"Warning: missing completion marker for {event}")
                continue
            duration = times["timestamps"][complete_ts] - timestamp
            # cganalysis does not have loops, so no "global" events
            df.loc[idx, :] = [experiment, "cganalysis", sample_name, event, duration, event]
            idx += 1
    return df, idx


def count_outputs(indirs, outdir, completions=6):
    """
    Count number of outputs for analyses.    
    """
    # Note that excess here only includes completions, we don't account for
    # jobs that started running and didn't save output (partial run or otherwise)
    df = pandas.DataFrame(columns=['experiment', 'job', 'count'])
    excess = pandas.DataFrame(columns=['experiment', 'job', 'count'])
    idx = 0
    for _indir in indirs:
        experiment = "gpu-static" if "gpu-static" in _indir else "cpu-static"
        data_dir = os.path.join(_indir, "data")
        # This is the total number of samples that were pushed from mlserver
        samples = [x for x in find_inputs(data_dir, "[.]gro") if "latest" in x]
        # Let's use mlsamples to represent mlserver or mlrunner
        df.loc[idx, :] = [experiment, 'mlsample', len(samples)]
        excess.loc[idx, :] = [experiment, "mlsample", len(samples) - completions]
        idx += 1
        createsims = [x for x in find_inputs(data_dir, "createsim") if "/createsim/" in x]
        df.loc[idx, :] = [experiment, 'createsim', len(createsims)]
        excess.loc[idx, :] = [experiment, "createsim", len(createsims) - completions]
        idx += 1
        cganalysis = [x for x in find_inputs(data_dir, "cganalysis") if "/cganalysis/" in x]
        df.loc[idx, :] = [experiment, 'cganlysis', len(cganalysis)]
        excess.loc[idx, :] = [experiment, "cganalysis", len(cganalysis) - completions]
        idx += 1
        
    print("Experiment Job Counts (completed with results)")        
    print(df)

    print("Excess Completed")   
    print(excess)
    df.to_csv(os.path.join(outdir, "jobs-completed.csv"))    
    excess.to_csv(os.path.join(outdir, "jobs-excess-completed.csv"))    


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


def parse_pulling_times(times):
    """
    Read events and turn into data frame with container pull times
    """
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

    # STRATEGY:
    # pod will get us pulling times
    # job will get us completion times (success or fail)
    #   jobs that do not complete in some respect are sunk cost
    #   that will be reflected in the total cluster up/down time
    for experiment, items in times.items():
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
                job_end = datetime.strptime(
                    item["events"]["completed"]["timestamp"], timestamp_format
                )
                job_start = datetime.strptime(
                    item["events"]["successfulcreate"]["timestamp"], timestamp_format
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
                parsed_timestamp = datetime.strptime(timestamp, timestamp_format)
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


def calculate_timings(summary_df, outdir):
    """
    Calculate experiment costs based on timings.
    TODO need to take costs into account
    """
    # Add the cost for the total cluster being up
    # This is multiplied by 6 for total nodes count
    summary_df.loc[idx, :] = ["gpu", "cluster-uptime", gpu_up_seconds * 6]
    idx += 1
    # summary_df.loc[idx, :] = ["cpu-manual", "cluster-uptime", cpu_up_seconds * 6]
    # idx += 1
    # summary_df.loc[idx, :] = ["gpu-manual", "cluster-uptime", gpu_manual_up_seconds * 6]
    # print(gpu_manual_up_seconds - gpu_up_seconds)

    summary_df.to_csv(os.path.join(outdir, "summary-times.csv"))
    make_plot(
        summary_df,
        title="Accumulated Times of Events Per Experiment",
        ydimension="duration",
        xdimension="event",
        outdir=img_outdir,
        ext="png",
        plotname="total_times_by_experiment",
        hue="experiment",
        palette=palette,
        plot_type="bar",
        xlabel="Event",
        ylabel="Total Time (seconds)",
        # do_log=True,
        # With log, no ylimit
        # ylim=None,
    )

    costs = {}

    # here is calculating the total experiment costs
    # this is from eksctl logs - when we see "node-x" ready
    # This was gpu run 2
    start_time = datetime.strptime("22:11:17", "%H:%M:%S")
    end_time = datetime.strptime("23:31:46", "%H:%M:%S")
    gpu_up_seconds = (end_time - start_time).seconds
    costs["gpu"] = 3.06 * (gpu_up_seconds / 60 / 60) * 6

    # This was cpu run 1
    # start_time = datetime.strptime("20:00:34", "%H:%M:%S")
    # end_time = datetime.strptime("22:22:45", "%H:%M:%S")
    # cpu_up_seconds = (end_time - start_time).seconds
    # costs["cpu-manual"] = 2.88 * (cpu_up_seconds / 60 / 60) * 6
    print(costs)


def plot_pulling_times(df, outdir):
    """
    Given an output directory, plot image to show pull times.
    """
    # Let's first plot pull times
    subset = df[df.event == "pulled"]
    # Don't account for already pulled
    subset = subset[subset.duration != 0]
    # Only include analysis containers
    subset = subset[subset.container.isin([x for x in subset.container.unique() if "mummi" in x])]
    img_outdir = os.path.join(outdir, "img")
    if not os.path.exists(img_outdir):
        os.makedirs(img_outdir)
    make_plot(
        subset,
        title="MuMMI Operator Container Pulling Times",
        ydimension="duration",
        xdimension="experiment",
        outdir=img_outdir,
        ext="png",
        plotname="pull_times_by_experiment",
        hue="experiment",
        plot_type="box",
        xlabel="Container",
        ylabel="Pull Time (seconds)",
        # do_log=True,
        # With log, no ylimit
        # ylim=None,
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
        title="MuMMI Operator Job Times By Experiment",
        ydimension="duration",
        xdimension="job",
        outdir=img_outdir,
        ext="png",
        plotname="job_times_by_experiment",
        hue="experiment",
        plot_type="box",
        xlabel="Job",
        ylabel="Running Time (seconds)",
        # do_log=True,
        # With log, no ylimit
        # ylim=None,
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
    plt.clf()
    return ax


def parse_pulling_data(outdir, files):
    """
    Parse events data for pulling containers.
    """
    # Assemble results across filenames - we will have mixing
    lookup = {}
    for filename in files:
        events = read_file(filename)
        sections = [x.strip() for x in events.split("\n") if x.strip()]

        # All unique events (reasons)
        # {'created',
        # 'killing',
        # 'noderegistrationcheckerdidnotrunchecks',
        # 'pulled',
        # 'pulling',
        # 'scalingreplicaset',
        # 'scheduled',
        # 'started',
        # 'successfulcreate'}
        environ = os.path.basename(os.path.dirname(filename))
        experiment = "gpu-static" if "gpu" in environ else "cpu-static"            

        # We have to separate results by experiment
        if experiment not in lookup:
            lookup[experiment] = {}

        # For each file, create lookup with container uid
        for section in sections:
            try:
                section = json.loads(section)
            except:
                print(f"Skipping non json {section}")
                continue

            # Discarded events
            if "reason" not in section:
                continue

            # unique id
            uid = section["metadata"]["name"].rsplit(".", 1)[0]
            kind = section["involvedObject"]["kind"]
            if uid not in lookup[experiment]:
                lookup[experiment][uid] = {
                    "events": {},
                    "experiment": experiment,
                    "kind": kind,
                }
            reason = section["reason"].lower()

            # Use event time and fall back to first time
            timestamp = section.get("eventTime") or section["firstTimestamp"]

            # Get the container URI from pulling
            if reason == "pulling":
                lookup[experiment][uid]["container"] = (
                    section["message"].rsplit(" ", 1)[-1].strip('"')
                )
            instance = section["reportingInstance"]
            lookup[experiment][uid]["events"][reason] = {
                "timestamp": timestamp,
                "instance": instance,
            }

            # If pulled, there is extra metadata about what it calculated
            if reason == "pulled":
                lookup[experiment][uid]["events"][reason]["message"] = section[
                    "message"
                ]

    # This is the primary raw data we are interested in.
    raw_times_file = os.path.join(outdir, "container-pulling-times.json")
    print(f"Saving raw container times to {raw_times_file}")
    write_json(lookup, raw_times_file)
    return lookup


if __name__ == "__main__":
    main()
