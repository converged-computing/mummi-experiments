import os
import time
import json
import tarfile
import re
import pandas
import seaborn as sns
from datetime import datetime
import matplotlib.pylab as plt
import matplotlib.ticker as ticker

timestamp_format = "%Y-%m-%dT%H:%M:%SZ"
node_timestamp_format = "%Y-%m-%dT%H:%M:%S.%fZ"

sns.set_theme(style="whitegrid", palette="tab10")


def read_file(filename):
    with open(filename, "r") as fd:
        content = fd.read()
    return content


# Set global colors for environments
colors = {}
color_palette = sns.color_palette()
for environ in [
    "mummi",
    "state machine",
    "state machine autoscale",
    "state machine flux",
    "on premises",
]:
    colors[environ] = color_palette.pop(0)

colors["flux state machine"] = colors["state machine flux"]

# Different plots use cpu/gpu
for environ in ["cpu", "cpu autoscale", "gpu", "gpu autoscale"]:
    colors[environ] = color_palette.pop(0)


def collect_inputs(_indirs, indir):
    """
    Given a lookup of experiment names and an input directory,
    assemble full paths and find event file names.
    """
    indirs = {}
    event_files = {}
    for experiment, indir_set in _indirs.items():
        indirs[experiment] = []
        event_files[experiment] = []
        for indir_name in indir_set:
            dirname = os.path.join(indir, indir_name)
            indirs[experiment].append(dirname)
            event_files[experiment] += find_inputs(dirname, "events-")
    return indirs, event_files


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
        times = json.loads(read_file(sample))
        sample_name = sample.split(os.sep)[-3]
        df, idx = parse_single_time_event(
            df,
            idx,
            times,
            experiment,
            iteration,
            sample_name,
            "createsim",
            multiple_runs,
        )
    return df, idx


def get_experiment_iteration(indir):
    """
    The experiment iteration is the numerical suffix.

    This function isn't used for on prem mummi.
    """
    dirname = os.path.basename(indir)
    try:
        # We also start counting at 0
        iteration = int(dirname.split("-")[-1])
        # Flux does not.
        if "flux" in indir:
            return iteration
        iteration += 1
    except:
        if "flux" in indir:
            raise ValueError(f"Issue getting iteration for {indir}")
        iteration = 0
    return iteration


def parse_cganalysis_times(df, samples, experiment, idx=0, iteration=0):
    """
    Parse timing output from cganalysis
    """
    for sample in samples:
        times = json.loads(read_file(sample))
        sample_name = sample.split(os.sep)[-3]
        df, idx = parse_single_time_event(
            df, idx, times, experiment, iteration, sample_name, "cganalysis"
        )
    return df, idx


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


def parse_timestamp(timestamp):
    """
    We either get an eventTime (considered atomic)
    or firstTimestamp (considered continuous). In practice
    I'm not sure the distinction makes sense, but the formats
    are slightly different.
    """
    if "." in timestamp:
        return datetime.strptime(timestamp, node_timestamp_format)
    return datetime.strptime(timestamp, timestamp_format)


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


def parse_pulling_times(times, outdir):
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
            "iteration",
        ]
    )
    idx = 0

    # STRATEGY:
    # pod will get us pulling times
    # job will get us completion times (success or fail)
    #   jobs that do not complete in some respect are sunk cost
    #   that will be reflected in the total cluster up/down time
    for experiment, iterations in times.items():
        for iteration, items in iterations.items():
            for uid, item in items.items():
                # Skip non-pod and job events for now
                kind = item["kind"]

                # Node is added here for autoscaling
                if kind not in ["Pod", "Job", "Node"]:
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
                        item["events"]["successfulcreate"]["timestamp"],
                        timestamp_format,
                    )
                    running_seconds = (job_end - job_start).seconds
                    job = uid.split("-")[0]

                elif kind == "Pod" and container is not None:
                    if "cganalysis" in container:
                        job = "cganalysis"
                    elif "createsim" in container:
                        job = "createsim"

                # We will parse these later
                elif kind == "Node":
                    # These are events we can see
                    # invaliddiskcapacity
                    # starting
                    # nodehasnodiskpressure
                    # nodehassufficientmemory
                    # nodeallocatableenforced
                    # nodehassufficientpid
                    # synced
                    # nodeready
                    # nodenotschedulable
                    for event_name, node_event in item["events"].items():
                        timestamp = node_event["timestamp"]
                        parsed_timestamp = parse_timestamp(timestamp)
                        df.loc[idx, :] = [
                            uid,
                            kind,
                            None,  # No job
                            event_name + "-timestamp",
                            parsed_timestamp.timestamp(),
                            node_event[
                                "instance"
                            ],  # Instead of container, we pull node id here
                            experiment,
                            iteration,
                        ]
                        idx += 1
                        continue

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
                    parsed_timestamp = parse_timestamp(timestamp)
                    df.loc[idx, :] = [
                        uid,
                        kind,
                        job,
                        event_name + "-timestamp",
                        parsed_timestamp.timestamp(),
                        container,
                        experiment,
                        iteration,
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
                            iteration,
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
                        iteration,
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
                        iteration,
                    ]
                    idx += 1
    df.to_csv(os.path.join(outdir, "container-pulling-times.csv"))
    return df


def parse_events(outdir, files):
    """
    Parse events data for pulling containers.
    """
    # Assemble results across filenames - we will have mixing
    lookup = {}
    nodes = {}
    for experiment, filenames in files.items():
        if experiment not in lookup:
            lookup[experiment] = {}
            nodes[experiment] = {}
        for filename in filenames:
            events = read_file(filename)
            iteration = get_experiment_iteration(os.path.dirname(filename))
            if iteration not in lookup[experiment]:
                lookup[experiment][iteration] = {}
                nodes[experiment][iteration] = {}
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

            # For each file, create lookup with container uid
            for section in sections:
                try:
                    section = json.loads(section)
                except:
                    print(f"Skipping non json {section}")
                    continue

                if "metadata" not in section:
                    continue

                # unique id
                uid = section["metadata"]["name"].rsplit(".", 1)[0]
                kind = section["involvedObject"]["kind"]
                if kind == "Node":
                    node_name = section["involvedObject"]["name"]
                    if node_name not in nodes[experiment][iteration]:
                        nodes[experiment][iteration][node_name] = {}
                    nodes[experiment][iteration][node_name][section["reason"]] = (
                        section["firstTimestamp"]
                    )
                    continue

                # Discarded events
                if "reason" not in section:
                    continue

                if uid not in lookup[experiment][iteration]:
                    lookup[experiment][iteration][uid] = {
                        "events": {},
                        "experiment": experiment,
                        "kind": kind,
                    }
                reason = section["reason"].lower()

                # Use event time and fall back to first time
                # eventTime is of atomic event, firstTimestamp The first timestamp of a continuous one
                # In practice, I don't see eventTime for events I'd consider atomic.
                # Note they have different formats...
                timestamp = section.get("eventTime") or section["firstTimestamp"]

                # Get the container URI from pulling
                if reason == "pulling":
                    lookup[experiment][iteration][uid]["container"] = (
                        section["message"].rsplit(" ", 1)[-1].strip('"')
                    )
                instance = section["reportingInstance"]
                lookup[experiment][iteration][uid]["events"][reason] = {
                    "timestamp": timestamp,
                    "instance": instance,
                }

                # If pulled, there is extra metadata about what it calculated
                if reason == "pulled":
                    lookup[experiment][iteration][uid]["events"][reason]["message"] = (
                        section["message"]
                    )

    # This is the primary raw data we are interested in.
    raw_times_file = os.path.join(outdir, "container-pulling-times.json")
    print(f"Saving raw container times to {raw_times_file}")
    write_json(lookup, raw_times_file)

    # Convert to data frame
    times_df = parse_pulling_times(lookup, outdir)
    return times_df, nodes


def count_outputs(
    indirs,
    outdir,
    completions=10,
    has_data_dir=True,
    mlrunner_tag="mlrunner",
    createsims_pattern="createsims.tar.gz",
    cganalysis_pattern="cganalysis",
):
    """
    Count number of outputs for analyses. This counts the new state machine operator
    output. MuMMI saves .tar.gz for each that need to be read into memory with a slightly
    differnet name, so we expose as variables.
    """
    # Note that excess here only includes completions, we don't account for
    # jobs that started running and didn't save output (partial run or otherwise)
    df = pandas.DataFrame(columns=["experiment", "job", "count", "iteration"])
    excess = pandas.DataFrame(columns=["experiment", "job", "count", "iteration"])
    idx = 0
    for experiment, indirset in indirs.items():
        for _indir in indirset:
            iteration = get_experiment_iteration(_indir)

            # The flux static experiments don't have a data directory, just one level up
            data_dir = _indir
            if has_data_dir:
                data_dir = os.path.join(_indir, "data")

            # This is the total number of samples that were pushed from mlserver
            # This tag is now automatically generated by the state machine operator, not latest
            samples = [x for x in find_inputs(data_dir, "[.]gro") if mlrunner_tag in x]
            # Let's use mlsamples to represent mlserver or mlrunner
            df.loc[idx, :] = [experiment, "mlsample", len(samples), iteration]
            excess.loc[idx, :] = [
                experiment,
                "mlsample",
                len(samples) - completions,
                iteration,
            ]
            idx += 1
            createsims = [
                x
                for x in find_inputs(data_dir, createsims_pattern)
                if "/createsim/" in x
            ]
            df.loc[idx, :] = [experiment, "createsim", len(createsims), iteration]
            excess.loc[idx, :] = [
                experiment,
                "createsim",
                len(createsims) - completions,
                iteration,
            ]
            idx += 1
            cganalysis = [
                x
                for x in find_inputs(data_dir, cganalysis_pattern)
                if "/cganalysis/" in x
            ]
            df.loc[idx, :] = [experiment, "cganalysis", len(cganalysis), iteration]
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


def parse_single_time_event(
    df, idx, times, experiment, iteration, sample_name, job_name, multiple_runs=None
):
    """
    Given a data frame, job name, and times lookup, parse into data frame
    """
    # Save all total durations
    for name, duration in times["times"].items():
        df.loc[idx, :] = [
            experiment,
            job_name,
            sample_name,
            name,
            duration,
            name,
            iteration,
        ]
        idx += 1

    # For all timestamps, calculate start to complete
    for name, timestamp in times["timestamps"].items():
        if "_start" not in name:
            continue
        event = name.replace("_start", "")

        # We will sum these totals at the end.
        global_event = event
        global_event_name = event.rsplit("_", 1)[0]
        if multiple_runs is not None and global_event_name in multiple_runs:
            global_event = global_event_name

        complete_ts = f"{event}_complete"
        if complete_ts not in times["timestamps"]:
            print(f"Warning: missing completion marker for {event}")
            continue

        duration = times["timestamps"][complete_ts] - timestamp
        if "cganalysis" == job_name and duration < 1600 and duration > 240:
            print("Found sample that is too small")
            print(f"Experiment: {experiment}")
            print(f"Sample name: {sample_name}")
            print(f"Duration: {duration}")
            print(f"Event: {global_event}")
            time.sleep(10)

        df.loc[idx, :] = [
            experiment,
            job_name,
            sample_name,
            event,
            duration,
            global_event,
            iteration,
        ]
        idx += 1
    return df, idx


def job_timings(indirs, outdir, has_data_dir=True):
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
            iteration = get_experiment_iteration(_indir)
            data_dir = _indir
            if has_data_dir:
                data_dir = os.path.join(_indir, "data")

            # This is the total number of samples that were pushed from mlserver
            samples = [
                x
                for x in find_inputs(data_dir, "createsims-times.json")
                if "/createsim/" in x
            ]
            df, idx = parse_createsim_times(df, samples, experiment, idx, iteration)

            samples = [
                x
                for x in find_inputs(data_dir, "cganalysis-times.json")
                if "/cganalysis/" in x
            ]
            df, idx = parse_cganalysis_times(df, samples, experiment, idx, iteration)

    # Calculate sum totals for events. E.g., some functions are run multiple times
    # Note that this is across samples and iterations within an experiment type
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
        height=12,
    )


def plot_pulling_times(df, outdir, include_mlrunner=True):
    """
    Given an output directory, plot image to show pull times.
    """
    # Let's first plot pull times
    subset = df[df.event == "pulled"]
    # Don't account for already pulled
    subset = subset[subset.duration != 0]
    # Only include analysis containers
    subset = subset[
        subset.container.isin([x for x in subset.container.unique() if "mummi" in x])
    ]
    img_outdir = os.path.join(outdir, "img")
    if not os.path.exists(img_outdir):
        os.makedirs(img_outdir)
    make_plot(
        subset,
        title="Container Pulling Times",
        ydimension="duration",
        xdimension="experiment",
        outdir=img_outdir,
        ext="png",
        plotname="pull_times_by_experiment",
        hue="experiment",
        plot_type="box",
        xlabel="Container",
        ylabel="Pull Time (seconds)",
    )
    print(subset.groupby(["experiment", "container"]).duration.mean())

    # Simplify into GPU, CPU, and Flux (Singularity)
    by_env = subset.copy()

    # Add mlrunner job labels to mlserver
    by_env.loc[by_env["container"].str.contains("mlserver"), "job"] = "mlrunner"

    # This get rid of containers not associated with a job
    by_env = by_env[~by_env.job.isna()]

    # This will be gpu or cpu
    machines = []
    jobs = []

    # This will be Kubernetes or Singularity and container
    environs = []
    for row in by_env.iterrows():
        if "mlrunner" in row[1].container or "mlserver" in row[1].container:
            job = "mlrunner"
        elif "createsim" in row[1].container:
            job = "createsim"
        elif "cganalysis" in row[1].container:
            job = "cganalysis"
        else:
            continue

        jobs.append(job)
        if "docker://" in row[1].container:
            environs.append("singularity")
        else:
            environs.append("containerd")
        if "cpu" in row[1].experiment:
            machines.append(f"{job}-cpu")
        else:
            machines.append(f"{job}-gpu")
    by_env["machine"] = machines
    by_env["tech"] = environs
    by_env.loc[:, "job"] = jobs

    make_plot(
        by_env,
        title="Container Pulling Times",
        ydimension="duration",
        xdimension="job",
        outdir=img_outdir,
        ext="png",
        plotname="pull_times_by_environment",
        hue="tech",
        plot_type="box",
        xlabel="Container",
        ylabel="Pull Time (seconds)",
        remove_legend=True,
        height=4,
        rotation=360,
    )
    print(by_env.groupby(["tech", "job"]).duration.mean())

    # Now let's look at time for each job
    # Let's first plot pull times
    subset = df[df.event == "running"]

    # These are jobs that never finished
    subset = subset[subset.duration < 30000]

    # These were failed cganalysis that didn't exit with non zero, so we could not react to
    # It must be an edge case error. E.g., see:
    # https://github.com/converged-computing/mummi-experiments/blob/main/experiments/aws-march-2025/state-machine-flux/results/cpu/iter-3/structure_048708132/cganalysis/md.log#L691
    subset = subset[~((subset.job == "cganalysis") & (subset.duration < 1500))]

    # Make a separate figure for each job type.
    for job in subset.job.unique():
        job_subset = subset[subset.job == job]

        labels = []
        job_environs = []
        for value in job_subset.experiment.values:
            job_environ = "gpu"
            if "cpu" in value:
                job_environ = "cpu"
            job_environs.append(job_environ)
            value = (
                value.replace("-static", "")
                .replace("-" + job_environ, "")
                .replace("-", " ")
            )
            labels.append(value)

        job_subset["labels"] = labels
        job_subset["job_environ"] = job_environs

        make_plot(
            job_subset,
            title=f'Job "{job}" Times By Experiment',
            ydimension="duration",
            xdimension="job_environ",
            outdir=img_outdir,
            ext="png",
            plotname=f"job_{job}_times_by_experiment",
            hue="labels",
            plot_type="box",
            palette=colors if "gpu autoscale" not in job_environs else None,
            order=["cpu", "gpu"],
            xlabel=None,
            ylabel="Running Time (seconds)",
            rotation=360,
            height=4,
            width=6,
            remove_legend=True,
            ymin=0,
            ymax=2100,
            remove_y=False if job == "mlrunner" else True,
        )

    # Let's do summary of job times
    by_job = subset.groupby(["job", "experiment", "iteration"])["duration"].sum()
    subset = df[df.event == "pulled"]
    by_pull = subset.groupby(["job", "experiment", "iteration"])["duration"].sum()
    print(by_job)
    print(by_pull)

    # Convert into data frame
    summary_df = pandas.DataFrame(
        columns=["experiment", "job", "event", "duration", "iteration"]
    )
    idx = 0
    for entry in by_job.items():
        summary_df.loc[idx, :] = [
            entry[0][1],
            entry[0][0],
            "running",
            entry[1],
            entry[0][2],
        ]
        idx += 1
    for entry in by_pull.items():
        summary_df.loc[idx, :] = [
            entry[0][1],
            entry[0][0],
            "pulled",
            entry[1],
            entry[0][2],
        ]
        idx += 1

    # We will add costs to this based on workflow running time
    return summary_df


def workflow_manager(indirs, outdir):
    """
    Look at timings for the workflow manager
    """
    # Keep a lookup for the exact workflow start timestamps
    workflow_starts = {}
    workflow_ends = {}
    df = pandas.DataFrame(
        columns=["experiment", "event", "duration", "global", "iteration"]
    )
    idx = 0
    for experiment, indirset in indirs.items():
        for _indir in indirset:
            iteration = get_experiment_iteration(_indir)
            times = read_json(os.path.join(_indir, "workflow-times.json"))
            if experiment not in workflow_starts:
                workflow_starts[experiment] = {}
                workflow_ends[experiment] = {}
            if iteration not in workflow_starts[experiment]:
                workflow_starts[experiment][iteration] = {}
                workflow_ends[experiment][iteration] = {}
            for name, timestamp in times["timestamps"].items():
                if "workflow_start" in name:
                    workflow_starts[experiment][iteration] = timestamp
                    workflow_end = times["timestamps"]["workflow_complete"]
                    workflow_ends[experiment][iteration] = workflow_end
                    duration = workflow_end - timestamp
                    df.loc[idx, :] = [
                        experiment,
                        name,
                        duration,
                        "workflow_complete",
                        iteration,
                    ]
                    idx += 1
                    continue

                # Everything else should be a structure event, and we derive
                # other events (succeeded, failed) from that
                if "structure_" not in name or "_start" not in name:
                    continue

                event = name.replace("_start", "")
                jobid, jobtype = event.rsplit("_", 1)

                # The job will either have failed or succeeded
                success_ts = f"{event}_succeeded"
                failure_ts = f"{event}_failed"
                if success_ts in times["timestamps"]:
                    duration = times["timestamps"][success_ts] - timestamp
                    df.loc[idx, :] = [
                        experiment,
                        jobtype,
                        duration,
                        f"{jobtype}_success",
                        iteration,
                    ]
                    idx += 1

                elif failure_ts in times["timestamps"]:
                    duration = times["timestamps"][failure_ts] - timestamp
                    df.loc[idx, :] = [
                        experiment,
                        jobtype,
                        duration,
                        f"{jobtype}_failure",
                        iteration,
                    ]
                    idx += 1

                else:
                    print(
                        f"Warning, {name} started but did not succeed or fail, likely ran the whole time."
                    )

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
    write_json(
        {"starts": workflow_starts, "ends": workflow_ends},
        os.path.join(outdir, "workflow-endpoint-times.json"),
    )
    # Remove functions that total sum across the workflow is < 1 second
    make_plot(
        df,
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
    total_time = df[df["global"].isin(["workflow_complete", "wfmanager_run_workflow"])]
    total_time["global"] = "workflow_complete"
    if "flux" in outdir:
        total_time["environment"] = [x.split("-")[1] for x in total_time["experiment"]]
    else:
        total_time["environment"] = [x.split("-")[0] for x in total_time["experiment"]]
    make_plot(
        total_time,
        title="Total Time to Run Workflow",
        ydimension="duration",
        xdimension="experiment",
        outdir=os.path.join(outdir, "img"),
        ext="png",
        plotname="workflow_total_time",
        hue="environment",
        plot_type="bar",
        xlabel="Environment",
        ylabel="Running Time (seconds)",
        rotation=360,
        height=3,
    )

    # The only meaningful comparison is the workflow running time to get all samples
    print("See workflow running time to get 10 completions")
    print(df.groupby(["experiment", "global"]).duration.mean())
    return df, workflow_starts, workflow_ends


def calculate_costs_static(indirs, manager_df, workflow_starts, workflow_ends, outdir):
    workflow_times = workflow_times_from_manager(manager_df)

    total_costs = {}
    for experiment, iterations in workflow_times.items():
        if experiment not in total_costs:
            total_costs[experiment] = {}
        for iteration, uptime in iterations.items():
            total_costs[experiment][iteration] = {}
            if "cpu" in experiment:
                total_costs[experiment][iteration] = (uptime / 60 / 60) * 1.683 * 6
            else:
                total_costs[experiment][iteration] = (uptime / 60 / 60) * 3.06 * 6

    # calculate whole cost of experiment assuming all nodes up
    # (they were, because experiment is static)
    plot_total_workflow_costs(total_costs, outdir)


def calculate_costs(
    indirs, times_df, manager_df, workflow_starts, workflow_ends, outdir
):
    """
    Calculate costs based on specific node times - this is for autoscaling.
    """
    # Read in cluster nodes events
    cluster_nodes = {}
    for experiment, indirset in indirs.items():
        for indir in indirset:
            if experiment not in cluster_nodes:
                cluster_nodes[experiment] = {}
            iteration = get_experiment_iteration(indir)
            cluster_nodes[experiment][iteration] = read_json(
                os.path.join(indir, "cluster-nodes.json")
            )

    # Now use cluster nodes metadata to determine when nodes were up vs. note
    total_times = {}
    compute_nodes = ["hpc7g.16xlarge", "p3.2xlarge"]
    for experiment, iterset in cluster_nodes.items():
        if experiment not in total_times:
            total_times[experiment] = {}
        for iteration, nodeset in iterset.items():
            total_times[experiment][iteration] = []
            for node_name, nodemeta in nodeset.items():
                # Filter nodes to just include those that are for compute (not sticky)
                if (
                    nodemeta["labels"]["node.kubernetes.io/instance-type"]
                    not in compute_nodes
                ):
                    continue
                # While the experiment design doesn't elicit this, we need to check for the
                # case that a node went away and came up during the experiment. This might
                # happen with an aggressive autoscaling policy.
                first_event = nodemeta["conditions"][0]["last_transition_time"]

                # By default we know the node is up at the start of the workfow
                # Check that the first event was before the cluster was created
                node_start_time = workflow_starts[experiment][iteration]

                # Did the node report ready the first time after the experiment started?
                if first_event > node_start_time:
                    print(f"Found node {node_name} that came up during experiment")
                    node_start_time = first_event

                # If the last event posted had the node not ready, it was removed at some point.
                if not nodemeta["is_ready"]:
                    last_event = nodemeta["conditions"][-1]
                    assert (
                        last_event["type"] == "Ready" and last_event["status"] is False
                    )
                    node_uptime = last_event["last_transition_time"] - node_start_time
                    total_times[experiment][iteration].append(node_uptime)
                # If the node remained ready, it was up the duration of the experiment
                else:
                    total_times[experiment][iteration].append(
                        workflow_ends[experiment][iteration] - node_start_time
                    )

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

    return plot_total_workflow_costs(total_costs, outdir)


def plot_total_workflow_costs(total_costs, outdir):
    """
    Plot and save data for total workflow times.
    """
    print(json.dumps(total_costs, indent=4))
    cost_df = pandas.DataFrame(
        columns=["experiment", "cost", "environment", "iteration"]
    )
    idx = 0
    for experiment, iterations in total_costs.items():
        for iteration, cost in iterations.items():
            if "autosc" in experiment:
                environ = "autoscale"
            elif "static" in experiment:
                environ = "static"
            elif "gpu" in experiment:
                environ = "gpu"
            elif "cpu" in experiment:
                environ = "cpu"
            else:
                raise ValueError(
                    f"Unknown experiment to find environment for: {experiment}"
                )
            cost_df.loc[idx, :] = [
                experiment.replace("-", " "),
                cost,
                environ,
                iteration,
            ]
            idx += 1

    cost_df.to_csv(os.path.join(outdir, "total-costs.csv"))
    make_plot(
        cost_df,
        title="Total Cost to Run Workflow",
        ydimension="cost",
        xdimension="experiment",
        outdir=os.path.join(outdir, "img"),
        ext="png",
        plotname="workflow_total_cost",
        hue="environment",
        plot_type="box",
        xlabel="Environment",
        ylabel="Cost ($)",
        rotation=360,
    )


# Shared functions for calculate_costs
def workflow_times_from_manager(manager_df):
    """
    Make a data frame of just times for workflow complete
    """
    workflow_times = {}
    for experiment in manager_df.experiment.unique():
        if experiment not in workflow_times:
            workflow_times[experiment] = {}
        subset = manager_df[manager_df.experiment == experiment]
        for iteration in subset.iteration.unique():
            # For one experiment, this is just one value
            workflow_times[experiment][iteration] = subset[
                (subset.iteration == iteration)
                & (manager_df["global"] == "workflow_complete")
            ].duration.mean()
    return workflow_times


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
    order=None,
    remove_legend=False,
    remove_y=False,
    remove_x=False,
    round_y=False,
    hue_order=None,
    xmin=None,
    xmax=None,
    ymin=None,
    ymax=None,
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
    sns.set_style("whitegrid")
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
            x=xdimension,
            y=ydimension,
            hue=hue,
            hue_order=hue_order,
            data=df,
            linewidth=0.8,
            palette=palette,
            order=order,
        )
    elif plot_type == "box":
        ax = plotfunc(
            x=xdimension,
            y=ydimension,
            hue=hue,
            data=df,
            linewidth=1.8,
            order=order,
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
    if remove_legend:
        ax.get_legend().set_title(None)
    if xmin is not None and xmax is not None:
        plt.xlim(xmin, xmax)
    if ymin is not None and ymax is not None:
        plt.ylim(ymin, ymax)
    plt.title(title)
    if round_y:
        ax.yaxis.set_major_formatter(ticker.FormatStrFormatter("%.2f"))
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.set_xticklabels(ax.get_xmajorticklabels(), fontsize=14)
    ax.set_yticklabels(ax.get_yticks(), fontsize=14)
    # sns.move_legend(ax, "upper left", bbox_to_anchor=(1, 1))
    if remove_x:
        ax.set_xlabel(None)
    if remove_y:
        ax.set_ylabel(None)
        ax.set_yticks([])
    plt.xticks(rotation=rotation)
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, f"{plotname}.svg"))
    plt.savefig(os.path.join(outdir, f"{plotname}.png"))
    plt.clf()
    return ax
