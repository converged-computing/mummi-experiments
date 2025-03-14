# State Machine Operator Experiment

> This paradigm is part of the Mummi experiments. Here we are testing using the State Machine Operator, which uses a state machine and removes some of the persistent services in favor of Kubernetes events

```bash
git clone https://github.com/converged-computing/mummi-experiments
cd ./mummi-experiments/experiments/aws-march-2025/state-machine-operator
```

Note that feedback files were generated and used, but not added here (there are a lot of files). Final results (all run on March 13, 2025)

 - cpu-arm-autoscale (March 13, 2025)
 - cpu-arm-no-autoscaling (March 13, 2025)
 - cpu-arm-no-autoscaling-0 (March 14, 2025)
 - gpu-autoscale (March 13, 2025)
 - gpu-no-autoscaling (March 13, 2025) 
 
## Experiments

There will be four experiments - one for GPU and one for CPU, and each with and without autoscaling. This means these commands each need to be done twice, and the first time without installing the autoscaler.

```bash
# GPU
eksctl create cluster --config-file ./crd/eks-config-gpu-autoscaling.yaml
aws eks update-kubeconfig --region us-east-1 --name mini-mummi-gpu

# CPU (ARM)
eksctl create cluster --config-file ./crd/eks-config-cpu-arm-autoscaling.yaml
aws eks update-kubeconfig --region us-east-1 --name mini-mummi
```

```bash
# This makes the monitor a sticky node
kubectl create namespace monitoring
# kubectl apply -f ./event-monitor-gpu
kubectl apply -f ./event-monitor-arm

# In a different terminal, this will save nodes and collect events.
# environ=cpu-arm-autoscale
environ=cpu-arm-no-autoscaling-1
region=us-east-1
instance=hpc7g.16xlarge

# environ=gpu-autoscale
# region=us-east-1
# instance=p3.2xlarge

mkdir -p ./monitor/${environ}
kubectl get nodes -o json > ./monitor/${environ}/nodes-$(date +%s).json

# Topology API (only for hpc instance types)
# Note that I was running an a la carte gpu instance in this region, needs to be filtered out
aws ec2 describe-instance-topology --region ${region} --filters Name=instance-type,Values=${instance} > ./monitor/${environ}/topology.json
aws ec2 describe-instances --filters "Name=instance-type,Values=${instance}" --region ${region}  > ./monitor/${environ}/instances.json
kubectl logs -n monitoring $(kubectl get pods -n monitoring -o json | jq -r .items[0].metadata.name) -f |& tee ./monitor/${environ}/events-$(date +%s).json
```

#### State Machine Operator

Install the operator. Note this requires pushing to a development registry, and you'd need to customize if you don't have access (you likely won't, but I doubt anyone will try to reproduce this).

```bash
# autoscaling: ad29dab058184607a9a734e43293486d82c4e388 March 13, 2025.
# One cpu run used the previous commit (no recorded_at time, which we don't use)
# These have sticky nodes
kubectl apply -f crd/state-machine-operator-cpu.yaml
kubectl apply -f crd/state-machine-operator-gpu.yaml
```

Run the Experiment. Note that since the resources here are going directly to Kubernetes, we ask for exactly what we want each job to have.

```bash
kubectl apply -f ./crd/cpu-arm-mummi-autoscale.yaml
kubectl apply -f ./crd/gpu-mummi-autoscale.yaml
```

Once the cluster is up, what I did is wait until the first round of work was done, and then installed the autoscaler (this has a node selector for the sticky node). Note you only need to do this for the experiments with autoscaling!

```bash
# For arm or cpu (these have different node selectors)
kubectl apply -f crd/cluster-autoscaler-cpu-arm.yaml
kubectl apply -f crd/cluster-autoscaler-gpu.yaml
```

Note that the registry and manager are annotated with a label to be assigned to the sticky node. They won't be evicted.

## Saving data files

When the workflow is complete, we can save the state, etc. First, get output for the different components. For each of the manager and registry, do:

```bash
# In a different terminal, this will save nodes and collect events.
environ=cpu-arm-no-autoscaling-1
# environ=cpu-arm-autoscale
# environ=gpu-no-autoscaling
# environ=gpu-no-autoscale

#kubectl logs <container>  > ./monitor/${environ}/<container>.out
kubectl get pods -o wide > ./monitor/${environ}/final-pods-state.txt
kubectl get pods -o json > ./monitor/${environ}/final-pods-state.json

# Copy times from the manager
kubectl cp mummi-manager-86ddd95986-5gctw:/workflow-times.json workflow-times.json
kubectl cp mummi-manager-55b864fb8f-z4wvl:/cluster-nodes.json ./cluster-nodes.json
kubectl get nodes -o wide > nodes.txt

# Autoscaler logs (if deployed)
kubectl logs -n kube-system cluster-autoscaler > cluster-autoscaler.out
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

## Cleanup

what did the jail officer tell his supervisor about the escaping shape.
he was there N-gone!

```bash
# GPU
kubectl delete -f crd/gpu-mummi-autoscale.yaml
eksctl delete cluster --config-file ./crd/eks-config-gpu-autoscaling.yaml

# CPU
kubectl delete -f crd/cpu-mummi-autoscale.yaml --wait
eksctl delete cluster --config-file ./crd/eks-config-cpu-arm-autoscaling.yaml --wait
```

## Quick Analysis

### Job Times

This shows mean job time for each component and environment environments.  When createsims failed (which it did several times for the cpu runs) it failed quickly. In practice the mlrunner runs in about ~200 seconds and it failed in ~73, so it added a few minutes extra for one node.

```console
experiment     global            
cpu-autoscale  cganalysis_success    1788.743308
               createsim_failure        72.50502
               createsim_success      508.113734
               mlrunner_success       200.432208
               workflow_complete     5006.600611
cpu-static     cganalysis_success    1788.690585
               createsim_failure       73.507765
               createsim_success      508.943212
               mlrunner_success       196.442478
               workflow_complete      5084.47364
gpu-autoscale  cganalysis_success    1886.150246
               createsim_failure       95.372141
               createsim_success       818.71359
               mlrunner_success        248.10401
               workflow_complete     5936.322261
gpu-static     cganalysis_success    1884.673229
               createsim_success      827.036506
               mlrunner_success       277.216349
               workflow_complete     5864.469944
```

Here are the total samples generated for each. CGanalysis always has 10 because that is the workflow manager's directed final state. We have extra for other components that correspond to the number of createsims failures. 

```console
Experiment Job Counts (completed with results)
       experiment         job count
0      cpu-static    mlsample    12
1      cpu-static   createsim    10
2      cpu-static  cganalysis    10
3   cpu-autoscale    mlsample    12
4   cpu-autoscale   createsim    10
5   cpu-autoscale  cganalysis    10
6      gpu-static    mlsample    10
7      gpu-static   createsim    10
8      gpu-static  cganalysis    10
9   gpu-autoscale    mlsample    11
10  gpu-autoscale   createsim    10
11  gpu-autoscale  cganalysis    10
```

We can see the failures represented in excess.

```bash
Excess Completed
       experiment         job count
0      cpu-static    mlsample     2
1      cpu-static   createsim     0
2      cpu-static  cganalysis     0
3   cpu-autoscale    mlsample     2
4   cpu-autoscale   createsim     0
5   cpu-autoscale  cganalysis     0
6      gpu-static    mlsample     0
7      gpu-static   createsim     0
8      gpu-static  cganalysis     0
9   gpu-autoscale    mlsample     1
10  gpu-autoscale   createsim     0
11  gpu-autoscale  cganalysis     0
```

Note that we have an extra job here (as compared to mummi-operator) because the mummi-operator runs the mlserver and doesn't represent that work as a job.

![results/img/job_times_by_experiment.png](results/img/job_times_by_experiment.png)

Here are times in a format easier to parse - these are the total summed times across jobs (so much longer than total experiment).

```console
experiment     global                           job       
cpu-autoscale  cganalysis_load_mdanalysis       cganalysis        6.416309
               cganalysis_main_analysis         cganalysis    17776.368806
               cganalysis_run                   cganalysis    17833.494761
               cganalysis_run_simulation        cganalysis       50.065535
               cganalysis_simrun                cganalysis       50.064521
                                                                  ...     
gpu-static     createsims_pull_molecules        createsim      4214.846921
               createsims_relax_protein         createsim        351.46814
               createsims_setup_cg_sim          createsim      7368.957432
               createsims_short_equilibration   createsim      2120.940203
               createsims_trjconv_lipids_water  createsim        12.746942
```

### Pull Times

These are total summed pulling times, just for containers relevant to mummi (the others are small and trivial anyway). Obviously GPU containers are bigger and take longer.

![results/img/pull_times_by_experiment.png](results/img/pull_times_by_experiment.png)

### Partial Job Excess

We don't have any partial job excess because the workflow stops when cganalysis == completions desired.

### Workflow Manager Times

Here are the accumulated worker node times. The autoscaling setups each have 2 nodes that were cleaned up early.

```console
{
    "cpu-static": [
        5084.473639726639,
        5084.473639726639,
        5084.473639726639,
        5084.473639726639,
        5084.473639726639,
        5084.473639726639
    ],
    "cpu-autoscale": [
        3121.6075434684753,
        2901.6075434684753,
        5006.600611209869,
        5006.600611209869,
        5006.600611209869,
        5006.600611209869
    ],
    "gpu-static": [
        5864.469943523407,
        5864.469943523407,
        5864.469943523407,
        5864.469943523407,
        5864.469943523407,
        5864.469943523407
    ],
    "gpu-autoscale": [
        3485.0780992507935,
        5936.32226061821,
        5936.32226061821,
        5936.32226061821,
        5936.32226061821,
        3475.0780992507935
    ]
}
```

And final costs.

```console
{
    "cpu-static": 14.261948559433222,
    "cpu-autoscale": 12.178196196105482,
    "gpu-static": 29.908796711969373,
    "gpu-autoscale": 26.099628454828263
}
```

![results/img/workflow_manager_times.png](results/img/workflow_manager_times.png)
![results/img/workflow_total_cost.png](results/img/workflow_total_cost.png)


### Function Times

![results/img/function_times_by_experiment.png](results/img/function_times_by_experiment.png)

