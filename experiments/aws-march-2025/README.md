# State Machine Experiment

We are going to test the following setups. We are going to do several experiments, aiming for 3 iterations of each, on a size 6 cluster, 10 completions of cganalysis, which will be either GPU or GPU, and allow autoscaling (removing nodes) or not if applicable. We will always start the cluster and experiments at the largest size, and the autoscaling will mostly be important for removing nodes at the end that are not being used. We will first test createsim to choose the optimal CPU instance type. For GPU we can only choose what is available that we can afford. See [notes.md](notes.md) for early thinking about design.

## Experiments

- [state-machine-operator-autoscaling](state-machine-operator-autoscaling): runs on CPU/GPU with the State Machine Operator, with and without autoscaling.
- [mummi-operator](mummi-operator): runs on CPU/GPU using the MuMMI Operator
- [state-machine-flux](state-machine-flux): runs on CPU/GPU with Virtual Machines using Flux

Note that [state-machine-operator](state-machine-operator) is not used, as it only ran to 6 completions and used an older version of the operator. The static runs for the state machine operator are in the autoscaling directory.

## Analysis

These are early results that summarize across experiments (they will be updated).

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
### Costs

This is the difference in cost between traditional MuMMI in Kubernetes vs. the State Machine Operator orchestration. The design decisions make a big difference. These are hpc6a (cpu) and p3 (gpu).  There are also fewer completions (only 6) so you can't compare to the cost plot for the autoscaling experiments, where we had 10 completions required.

![results/img/workflow_total_cost.png](results/img/workflow_total_cost.png)


