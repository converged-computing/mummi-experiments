# State Machine Experiment

We are going to test the following setups. We are going to do 10 total completions on a size 6 cluster, which will be either GPU or GPU, and allow autoscaling (removing nodes) or not. We will always start the cluster and experiments at the largest size, and the autoscaling will mostly be important for removing nodes at the end that are not being used.

## Overview

I think we should first do experiments that show incremental improvement on different facets of Mummi, with respect to design, and then CPU and GPU (described below). I then think we should choose the best setup and do one more "production" cloud run, maybe with better GPU and larger, and then we can do further looking at the results (or similar).

- Mummi Operator on AWS (represents the old design where the ML server requires an entire node)
   - For each of CPU and GPU (this will assess the tradeoff between the two, assuming limit of cganalysis time)
- State Machine Operator on AWS
   - For each of CPU and GPU (this will assess the tradeoff between the two, assuming limit of cganalysis time)
   - For each of CPU and GPU starting at max size and allowing cluster to downscale
- State Machine Operator with Singularity and Flux (Bare Metal AWS)
   - For each of CPU and GPU (if possible)

That will be 8 experiments total. Autoscaling is not done for the Mummi Operator because it would not make a difference - the stopping point is manual and the cluster will remain filled until the end. For Kubernetes setups, I can collect metadata about image pulls and events. For the state machine operator runs I can collect additional timings of the orchestration. These are the comparisons we can make:

- CPU vs. GPU for each setup and between setups
- Bare Metal vs. Kubernetes, where notably, Kubernetes can have autoscaling
- The improvement to Mummi removing rabbitMQ and the MLServer vs running the ML as a single job
- Container pulling times between the setups

For CPU nodes, we will ask for 94/96 cores per task. For GPU, since the GPU has 1/node, that specification on the request will handle the scheduling topology. You will need the repository root here to create the clusters, etc.

```bash
git clone https://github.com/converged-computing/mummi-experiments
cd ./mummi-experiments/experiments/aws-march-2025
```

Note that the State Machine Operator setup requires the mlrunner container, which is deployed from the [mummi-operator](https://github.com/converged-computing/mummi-operator). 


## Metrics to Collect

 - Timing for events (Kubernetes and via the manager)
 - Total time for experiment (able to calculate cost for entire cluster)
 - Number of outputs for each step produced (e.g., the ML server produces too many)
 - Excess of outputs (iterations from ML server AND additional jobs that can't be used)
 - A cool angle would be to use the cost analyzer to run a mock workflow with different designs

## Discussion and Questions

 - The scale for the experiments (see suggestion above)
    - 6 state machines (18 jobs total) for Mummi Operator comparison
    - 10 jobs total for setups that afford downsizing.
    - Need a way to monitor when nodes come up and down (Kubernetes event exporter?)
    - For node types, GPU and CPU
 - Run experiments on different clusters
 - We are stopping cganalysis at 30 minutes
 - Save all output data (includes timings)
 - Other features I am forgetting? Vertical pod autoscaling?
 - For AWS, I'm having trouble with getting the shared storage working (at least haven't yet). 
 
High level, because we are demonstrating the features moreso than mummi, I think cutting at 30 minutes (or even sooner) is reasonable. I also don't think the output of Mummi is as important as the overall timings, unless there is something interesting with respect to performance on CPU vs. GPU. We will save everything regardless.

## TODO Vanessa

- Come up with random patterns to run simulations of workflows with the state machine operator.

## Experiments

The sections below show how to do a run of either a CPU or GPU experiment. The run number will create a hierarchy under either [data](data) or [monitor](monitor).

### AWS Bare Metal

Deploy the setup.  This will be moved to a different directory (organized with data, etc.) when run.

```bash
# Choose one
cd tf-aws-gpu
cd tf-aws-cpu
make
```

Then get the lead instance IP and shell in. Experiment orchestration underway.

TBA. Note to self - I rebuilt the GPU image with GPU pulls and my authorized key added, and it needs testing with the GPU workflow and a shared filesystem. I tested the CPU setup on an older flux install, and that would need a rebuild that also has the authorized key. 

And note to delete, I had trouble with make destroy and the autoscaling group. I needed to delete both the storage and autoscaling group manually.

```console
# Storage
aws delete-file-system --file-system-id mummi-gpu-efs --region us-east-1
aws delete-file-system --file-system-id mummi-cpu-efs --region us-east-2

# Autoscaling
aws autoscaling delete-auto-scaling-group --force-delete --auto-scaling-group-name flux-autoscaling-group --region us-east-1
aws autoscaling delete-auto-scaling-group --force-delete --auto-scaling-group-name flux-autoscaling-group --region us-east-2
```

#### Setup

We need to clone and install the state machine operator.

```bash
# a88dfe2f98c46896f499a52754eb906fef67eb43 March 5, 2025
git clone https://github.com/converged-computing/state-machine-operator
cd state-machine-operator
```
Install to python:

```bash
sudo python3 -m pip install -e ./python/
```

And you will need the repository root here to create the clusters.

```bash
cd ../
git clone https://github.com/converged-computing/mummi-experiments
```

The containers should already be pulled and data extracted. 
Create the working directory to run

```bash
flux exec -r all mkdir -p /home/ubuntu/workdir
cd /home/ubuntu/workdir
# For some reason flux not on PYTHONPATH
export PYTHONPATH=/usr/lib/python3.10/site-packages

# TODO change this to repository path
# Start the manager to start the workflow. We assume flux is running
state-machine-manager start ./local/cpu/state-machine-workflow.yaml --config-dir=./local/cpu --scheduler flux --filesystem --workdir /home/ubuntu/workdir
```

Note that we will need to unmount the efs filesystem before destroy:

```bash
sudo umount /mnt/efs

# Haven't tested this yet
flux exec -r all sudo umount /mnt/efs
```

## Analysis

These are early results - these don't include autoscaling and need to be improved upon, etc.

### Completed Jobs By Experiment

These plots show that the MuMMI Operator generates far more outputs (completed) than we need.  This doesn't include a handful that were running and not completed when we hit 6 cganalysis samples. None of them have extra cganalysis because we stopped at exactly 6.

![results/img/completed_jobs_by_experiment.png](results/img/completed_jobs_by_experiment.png)
![results/img/excess_jobs_by_experiment.png](results/img/excess_jobs_by_experiment.png)

### Function Times by Experiment

This shows that the actual running of the steps does not vary based on the orchestrator. I'm not sure how they would (and would be worried if they did).

![results/img/function_times_by_experiment.png](results/img/function_times_by_experiment.png)

```console
experiment         global                            
mummi-cpu          wfmanager_add_cgframes_to_ml             0.000026
                   wfmanager_add_new_patches_mlserver       0.353598
                   wfmanager_add_new_patches_to_ml          0.000018
                   wfmanager_init_mlserver                  0.019922
                   wfmanager_init_scheduling                0.000901
                   wfmanager_run_workflow                6347.938754
                   wfmanager_setup                          0.029337
                   wfmanager_update_jobs                    1.189913
mummi-gpu          wfmanager_add_cgframes_to_ml             0.000050
                   wfmanager_add_new_patches_mlserver       2.732789
                   wfmanager_add_new_patches_to_ml          0.000033
                   wfmanager_init_mlserver                  0.020115
                   wfmanager_init_scheduling                0.001608
                   wfmanager_run_workflow                5630.112581
                   wfmanager_setup                          0.049022
                   wfmanager_update_jobs                    1.521514
state-machine-cpu  cganalysis_success                    1874.858176
                   createsim_success                     1140.086041
                   mlrunner_failure                        36.617095
                   mlrunner_success                        38.108823
                   workflow_complete                     3101.351853
state-machine-gpu  cganalysis_success                    1946.960304
                   createsim_success                      877.742465
                   mlrunner_failure                       450.427124
                   mlrunner_success                       376.669176
                   workflow_complete                     3327.152879
```

### Job Times by Experiment

The MLRunner job is unique to the State Machine Operator so it only is there. The means / distributions seems comparable.

![results/img/job_times_by_experiment.png](results/img/job_times_by_experiment.png)

```console
job         experiment       
cganalysis  mummi-cpu            11011
            mummi-gpu             9322
            state-machine-cpu    11251
            state-machine-gpu    11683
createsim   mummi-cpu            11671
            mummi-gpu             7058
            state-machine-cpu     6840
            state-machine-gpu     5266
mlrunner    state-machine-cpu     2352
            state-machine-gpu     2259
```

### Pull Times By Experiment

This variation seems large, but it's only a handful of pulls per cluster. I expect this is more of a result of AWS not having a global caching strategy (and generally being less consistent than say, Google Cloud) than anything else. I have lots of pulling data from test runs we could combine here to get a more extensive result.

![results/img/pull_times_by_experiment.png](results/img/pull_times_by_experiment.png)

```console
mummi-cpu             864.742588
mummi-gpu            2098.687371
state-machine-cpu     2273.73425
state-machine-gpu    4037.924493
```

### Workflow Manager Times

This has events that aren't comparable, except for two (with different names)...

![results/img/workflow_manager_times.png](results/img/workflow_manager_times.png)

And then we can compare to see the start differences in total workflow running time.

![results/img/workflow_total_time.png](results/img/workflow_total_time.png)

```console
             experiment                   event     duration             global       operator environment
1             mummi-cpu  wfmanager_run_workflow  6347.938754  workflow_complete          mummi         cpu
1701          mummi-gpu  wfmanager_run_workflow  5630.112581  workflow_complete          mummi         gpu
0     state-machine-cpu          workflow_start  3101.351853  workflow_complete  state-machine         cpu
21    state-machine-gpu          workflow_start  3327.152879  workflow_complete  state-machine         gpu
```

