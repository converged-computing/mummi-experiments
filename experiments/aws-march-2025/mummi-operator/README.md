# Mummi Operator Experiment

> This paradigm is part of the Mummi experiments. Here we are testing using the Mummi Operator, which uses the mlserver and rabbitmq for work.

We won't run autoscaling with the Mummi Operator, the reason being that it doesn't make a difference. Traditional mummi has no understanding of when it is done, so jobs continue to be submitted, so autoscaling would not kick in to downscale the cluster. Note that to get the exact digests for containers used, see the final-pods-state.json files in the monitor sub-directories here. If we run 10 samples completed here (no autoscaling) using the hpc7g we can compare to the other experiments, e.g., the static case of the state machine operator. Note that the first set of runs is under [monitor/6-completions-hpc6a](monitor/6-completions-hpc6a).

```bash
git clone https://github.com/converged-computing/mummi-experiments
cd ./mummi-experiments/experiments/aws-march-2025/mummi-operator
```
Final results:

 - gpu-static-0
 - gpu-static-1
 - gpu-static-2


## Experiments

There will be two experiments, - one for GPU and one for CPU.

```bash
# GPU
eksctl create cluster --config-file ../eks-config-gpu-static.yaml
aws eks update-kubeconfig --region us-east-1 --name mini-mummi-gpu

# CPU
eksctl create cluster --config-file ./crd/eks-config-cpu.yaml 
aws eks update-kubeconfig --region us-east-1 --name mini-mummi
```

```bash
# In a different terminal, this will save nodes and collect events.
environ=cpu-static-1
region=us-east-1
instance=hpc7g.16xlarge

# environ=gpu-static-2
# region=us-east-1
# instance=p3.2xlarge

kubectl create namespace monitoring
kubectl apply -f ../../../event-monitor

mkdir -p ./monitor/${environ}
kubectl get nodes -o json > ./monitor/${environ}/nodes-$(date +%s).json

# Topology API (only for hpc instance types)
# Note that I was running an a la carte gpu instance in this region, needs to be filtered out
aws ec2 describe-instance-topology --region ${region} --filters Name=instance-type,Values=${instance} > ./monitor/${environ}/topology.json
aws ec2 describe-instances --filters "Name=instance-type,Values=${instance}" --region ${region}  > ./monitor/${environ}/instances.json

kubectl logs -n monitoring $(kubectl get pods -n monitoring -o json | jq -r .items[0].metadata.name) -f |& tee ./monitor/${environ}/events-$(date +%s).json
```

#### Mummi Operator

This is private, so we install from a local build.

```bash
# commit used for GPU and CPU final runs: c1c45464eaa360116cb7ab6b1787b46bbcbf2ad7
git clone https://github.com/converged-computing/mummi-operator
cd mummi-operator
make test-deploy-recreate

# For arm, this has a node selector for the m6 node.
kubectl apply -f crd/mummi-operator-arm.yaml
```

Run the Experiment:

```bash
kubectl apply -f ./crd/gpu-mummi.yaml
kubectl apply -f ./crd/cpu-mummi.yaml
```

Note that the mummi-operator wfmanager is not resilient to starting. If this is the case, you can delete the pod and it will be re-created. 

## Saving data files

When the workflow is complete, we can save the state, etc. First, get output for the different components. For each of the mlserver, rabbitmq, and wfmanager, do:

```bash
# In a different terminal, this will save nodes and collect events.
environ=gpu-static-2
# environ=cpu-static-1

environ=cpu-static-0
#kubectl logs <container>  > ./monitor/${environ}/<container>.out
kubectl get pods -o wide > ./monitor/${environ}/final-pods-state.txt
kubectl get pods -o json > ./monitor/${environ}/final-pods-state.json
```

I found the easiest thing to do was expose the headless service, and then oras pull to my local machine.

```bash
# In another terminal
kubectl port-forward registry-0 5000:5000
oras repo ls localhost:5000

mkdir -p ./monitor/$environ/data
cd ./monitor/$environ/data
oras repo ls localhost:5000 > repos.txt
# Download artifacts organized by structure (repo) and step (tag)
registry=localhost:5000
root=$(pwd)
for repo in $(oras repo list --plain-http $registry) 
  do 
    for tag in $(oras repo tags --plain-http $registry/$repo)
      do 
        mkdir -p $root/$repo/$tag
        cd $root/$repo/$tag
        oras pull --plain-http $registry/$repo:$tag
    done
done
```

For the workflow manager to get times:

```bash
pixi shell
pixi add htop
# get wfmanager process
htop
kill -s SIGINT <process_id>
kill -s SIGINT 100
kill -s SIGINT 337
```

## Cleanup

```bash
# GPU
kubectl delete -f crd/gpu-mummi.yaml
eksctl delete cluster --config-file ../eks-config-gpu-static.yaml --wait

# CPU
kubectl delete -f crd/cpu-mummi.yaml
eksctl delete cluster --config-file ./crd/eks-config-cpu.yaml --wait
```

## Notes

- For the gpu-static-1 runs, one of the createsims ran the entire duration of the study, meaning there was only one node for createsims. It increased the time by 1.5x likely, and the study (cost) is going to be hugely impacted by it.
- For the gpu-static-0 run, there was one failed createsims at ~13 minutes. Although it was replaced, it meant we extended the workflow by that amount of time (and maybe more since cganalysis wouldn't have a sample to process).
- For the CPU runs, where there is an error (and the job is deleted) and a temporary change to the number of createsims job, the condition kicks in to generate more samples, and typically multiple iterations run to generate more samples than are needed. We would want this to happen, but for the sample generation to be more tightly linked with what is needed for createsims. For example, we only needed one sample here, but multiple loops were run to generate about 10 more.
- I consistently was able to stop the workflow (and get times) within 5 seconds of the 10th sample completing. Stressful, yes.

Also see [notes](notes.md) from testing runs.

## Quick Analysis

Notes:

 - There was one createsims job in the GPU run that never completed, so its running time is the full workflow. It's an outlier that is removed from the plot.
 - The workflow and analysis times are filtered to not include anything < 1 second
 
These are just some quick glances at a small amount of data for the runs here. I still need to add the state machine operator runs, do autoscaling runs, add both to these plots, then calculate costs. These are only moderately interesting to suggest that GPU is faster than CPU for this one setup using the MuMMI Operator (and costs TBA). I can guarantee you the state machine operator is much faster to do the same work! Some quick glances at output - this is hugely incomplete because we aren't comparing to anything interesting, but it's a start to parsing results.

### Job Times

This shows total job times for each job type between environments. The createsim cpu static was hurt because one of the jobs ran for the entire lifecycle of the workflow, occupying an entire node, and never finished. This means we ran with 1 instead of 2 nodes for that entire job family, which I imagine at least 1.5x the time.  These are mean job times:

```console
job         experiment
cganalysis  cpu-static    11011
            gpu-static     9322
createsim   cpu-static    11671
            gpu-static     7058
```

![results/img/job_times_by_experiment.png](results/img/job_times_by_experiment.png)

Here are times in a format easier to parse - these are the total summed times across jobs (so much longer than total experiment).

```console
experiment  global                                  job         iteration
gpu-static  cganalysis_load_mdanalysis              cganalysis  1                8.431115
                                                                2                8.427434
                                                                3                8.364358
            cganalysis_main_analysis                cganalysis  1            19561.218339
                                                                2            19561.327647
                                                                3            19561.236997
            cganalysis_run                          cganalysis  1            19625.696573
                                                                2            19625.811989
                                                                3            19625.647382
            cganalysis_run_simulation               cganalysis  1                55.11518
                                                                2                55.12998
                                                                3               55.119656
            cganalysis_simrun                       cganalysis  1               55.113516
                                                                2               55.128362
                                                                3               55.118126
            createsim_runtime                       createsim   1            15150.351368
                                                                2            14426.596093
                                                                3            13931.462085
            createsims_create_cg_patch              createsim   1                0.024352
                                                                2                 0.02297
                                                                3                0.020899
            createsims_generate_velocities          createsim   1              977.439474
                                                                2              921.894407
                                                                3              893.430991
            createsims_gromacs_energy_minimization  createsim   1               33.362308
                                                                2               63.584764
                                                                3               51.335348
            createsims_gromacs_make_ndx             createsim   1                9.681733
                                                                2                9.197189
                                                                3                8.200823
            createsims_mdrun_lipids_water           createsim   1                77.37339
                                                                2              127.941104
                                                                3              103.424371
            createsims_prime_cg_sim                 createsim   1               30.047769
                                                                2                28.39332
                                                                3               25.872878
            createsims_pull_molecules               createsim   1              8796.25375
                                                                2             8312.419094
                                                                3             8058.163145
            createsims_relax_protein                createsim   1              726.767629
                                                                2              687.674484
                                                                3              654.472362
            createsims_setup_cg_sim                 createsim   1            15119.864793
                                                                2            14397.791137
                                                                3            13905.211739
            createsims_short_equilibration          createsim   1             4432.255942
                                                                2             4192.582493
                                                                3             4065.234242
            createsims_trjconv_lipids_water         createsim   1                7.866728
                                                                2               14.994044
                                                                3               11.995622

```

![results/img/function_times_by_experiment.png](results/img/function_times_by_experiment.png)


### Pull Times

These are total summed pulling times, just for containers relevant to mummi (the others are small and trivial anyway). Obviously GPU containers are bigger and take longer.

```console
experiment
cpu-static     864.742588
gpu-static    2098.687371
Name: duration, dtype: object
```

![results/img/pull_times_by_experiment.png](results/img/pull_times_by_experiment.png)

### Job Counts Completed

These are job completions, as assessed by the output that we have. Note that this does not include jobs that were running and didn't complete.

```console
Experiment Job Counts (completed with results)
   experiment         job count
0  cpu-static    mlsample    32
1  cpu-static   createsim    10
2  cpu-static  cganalysis     6
3  gpu-static    mlsample   478
4  gpu-static   createsim     8
5  gpu-static  cganalysis     6
```

Given we needed just 6, here are excess.

```console
Excess Completed
   experiment         job count
0  cpu-static    mlsample    26
1  cpu-static   createsim     4
2  cpu-static  cganalysis     0
3  gpu-static    mlsample   472
4  gpu-static   createsim     2
5  gpu-static  cganalysis     0
```

The mlsample generates quickly enough that we will not have any partial results (generated but not done).

### Partial Job Excess

These are running that started but didn't complete. You can look at the final-pod-state.txt in each output directory to see where this comes from. These are in _addition_ to the excess above in terms of time. We could likely calculate the extra cost of these extra completed runs and incompleted partial runs.

### Workflow Manager Times

We can look at summed times for the workflow manager, and really there are only a few that add up to anything significant.

```console
experiment  global                              iteration
gpu-static  wfmanager_add_cgframes_to_ml        1               0.012286
                                                2                 0.0433
                                                3               0.044235
            wfmanager_add_new_patches_mlserver  1             223.315779
                                                2             440.865401
                                                3             905.166811
            wfmanager_add_new_patches_to_ml     1               0.012152
                                                2               0.016006
                                                3               0.038236
            wfmanager_init_mlserver             1               0.019449
                                                2               0.020555
                                                3               0.019488
            wfmanager_init_scheduling           1               0.001737
                                                2               0.001934
                                                3               0.001754
            wfmanager_run_workflow              1            8373.337833
                                                2            8418.256583
                                                3            8635.900259
            wfmanager_setup                     1               0.046443
                                                2               0.053153
                                                3               0.047636
            wfmanager_update_jobs               1              808.27233
                                                2            2185.037902
                                                3            2125.824929
```
