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
 - cpu-static-0
 - cpu-static-1

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
environ=cpu-static-2
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
environ=cpu-static-2
# environ=cpu-static-1

environ=cpu-static-2
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
cd $root
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
- I consistently was able to stop the workflow within 30 seconds of the 10th sample completing. Stressful, yes. I think a better "end" indicator to use will be the 10th completed cganalysis run, which won't have human variability.

Also see [notes](notes.md) from testing runs.

## Quick Analysis

Notes:

 - The workflow and analysis times are filtered to not include anything < 1 second
 
### Job Times

This should be total accumulated time for each job type and iteration.

```console
job         experiment  iteration
cganalysis  cpu-static  1            21552
                        2            21574
                        3            19782
            gpu-static  1            20269
                        2            20255
                        3            20228
createsim   cpu-static  1             6446
                        2             7581
                        3             9394
            gpu-static  1            16954
                        2            16199
                        3            14833
```

![results/img/job_times_by_experiment.png](results/img/job_times_by_experiment.png)

And function times by experiment.

![results/img/function_times_by_experiment.png](results/img/function_times_by_experiment.png)


### Pull Times

These are total summed pulling times, just for containers relevant to mummi (the others are small and trivial anyway). Obviously GPU containers are bigger and take longer.

![results/img/pull_times_by_experiment.png](results/img/pull_times_by_experiment.png)

### Job Counts Completed

These are job completions, as assessed by the output that we have. Note that this does not include jobs that were running and didn't complete.

```console
Experiment Job Counts (completed with results)
    experiment         job count iteration
0   gpu-static    mlsample    38         1
1   gpu-static   createsim    19         1
2   gpu-static  cganalysis    11         1
3   gpu-static    mlsample    28         2
4   gpu-static   createsim    18         2
5   gpu-static  cganalysis    11         2
6   gpu-static    mlsample   256         3
7   gpu-static   createsim    16         3
8   gpu-static  cganalysis    11         3
9   cpu-static    mlsample   640         1
10  cpu-static   createsim    13         1
11  cpu-static  cganalysis    11         1
12  cpu-static    mlsample    34         2
13  cpu-static   createsim    15         2
14  cpu-static  cganalysis    12         2
15  cpu-static    mlsample    20         3
16  cpu-static   createsim    19         3
17  cpu-static  cganalysis    11         3
```

The MLServer gets a little trigger happy when there is some state that crosses the threshold and it is triggered to generate samples. Given we needed just 10, here are excess.

```console
Excess Completed
    experiment         job count iteration
0   gpu-static    mlsample    28         1
1   gpu-static   createsim     9         1
2   gpu-static  cganalysis     1         1
3   gpu-static    mlsample    18         2
4   gpu-static   createsim     8         2
5   gpu-static  cganalysis     1         2
6   gpu-static    mlsample   246         3
7   gpu-static   createsim     6         3
8   gpu-static  cganalysis     1         3
9   cpu-static    mlsample   630         1
10  cpu-static   createsim     3         1
11  cpu-static  cganalysis     1         1
12  cpu-static    mlsample    24         2
13  cpu-static   createsim     5         2
14  cpu-static  cganalysis     2         2
15  cpu-static    mlsample    10         3
16  cpu-static   createsim     9         3
17  cpu-static  cganalysis     1         3
```

### Workflow Manager Times

We can look at summed times for the workflow manager, and really there are only a few that add up to anything significant.

```console
experiment  global                              iteration
cpu-static  wfmanager_add_cgframes_to_ml        1               0.008896
                                                2               0.004282
                                                3               0.005283
            wfmanager_add_new_patches_mlserver  1            1098.954367
                                                2             202.933205
                                                3             246.286833
            wfmanager_add_new_patches_to_ml     1               0.008777
                                                2               0.003732
                                                3               0.004627
            wfmanager_init_mlserver             1               0.018468
                                                2               0.020699
                                                3               0.019409
            wfmanager_init_scheduling           1               0.000985
                                                2               0.000996
                                                3               0.001035
            wfmanager_run_workflow              1            7769.607348
                                                2            9006.884279
                                                3            7836.949777
            wfmanager_setup                     1               0.039344
                                                2               0.039282
                                                3               0.039867
            wfmanager_update_jobs               1            2224.119616
                                                2             913.620913
                                                3            1182.220609
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
            wfmanager_run_workflow              1            8373.977172
                                                2            8410.330676
                                                3            8365.299786
            wfmanager_setup                     1               0.046443
                                                2               0.053153
                                                3               0.047636
            wfmanager_update_jobs               1              808.27233
                                                2            2185.037902
                                                3            2125.824929
Name: duration, dtype: object
```

