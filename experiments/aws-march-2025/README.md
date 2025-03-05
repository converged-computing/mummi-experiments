# State Machine Experiment

We are going to test the following setups. Note that a final design (e.g., number of completed jobs) will need to be decided. I am thinking to aim for 10 runs total with a size 3 cluster, and for autoscaling, allowing to scale up to 6.

## Overview

I think we should first do experiments that show incremental improvement on different facets of Mummi, with respect to design, and then CPU and GPU (described below). I then think we should choose the best setup and do one more "production" cloud run, maybe with better GPU and larger, and then we can do further looking at the results (or similar).

- Mummi Operator on AWS (represents the old design where the ML server requires an entire node)
   - For each of CPU and GPU (this will assess the tradeoff between the two, assuming limit of cganalysis time)
   - For each of CPU and GPU with autoscaling allowed
- State Machine Operator on AWS
   - For each of CPU and GPU (this will assess the tradeoff between the two, assuming limit of cganalysis time)
   - For each of CPU and GPU with autoscaling allowed
- State Machine Operator with Singularity and Flux (Bare Metal AWS)
   - For each of CPU and GPU (if possible)

That will be 10 experiments total. For Kubernetes setups, I can collect metadata about image pulls and events. For the state machine operator runs I can collect additional timings of the orchestration. These are the comparisons we can make:

- CPU vs. GPU for each setup and between setups
- Bare Metal vs. Kubernetes, where notably, Kubernetes can have autoscaling (but doesn't need to)
- The improvement to Mummi removing rabbitMQ and the MLServer vs running the ML as a single job
- Container pulling times between the setups

For CPU nodes, we will ask for 94/96 cores per task. For GPU, since the GPU has 1/node, that specification on the request will handle the scheduling topology. You will need the repository root here to create the clusters, etc.

```bash
git clone https://github.com/converged-computing/mummi-experiments
cd ./mummi-experiments/experiments/aws-march-2025
```

Note that the State Machine Operator setup requires the mlrunner container, which is deployed from the [mummi-operator](https://github.com/converged-computing/mummi-operator). 

## Discussion and Questions

 - The scale for the experiments (see suggestion above)
 - The scale for the follow up production run (and if this is a good idea, what are we demonstrating)?
 - Should we run the operators on the same clusters or generate new ones?
 - Are we stopping cganalysis at 30 minutes (I'm not sure we can afford it if we don't)
 - Is there benefit to saving output data for the simulation if we cut at 30 minutes?
 - autoscaling sizes up to what?
 - events to wrap in the state machine operator?
 - local configs (for each of CPU and GPU)?
 - other features I am forgetting?
 
High level, because we are demonstrating the features moreso than mummi, I think cutting at 30 minutes (or even sooner) is reasonable. I also don't think the output of Mummi is as important as the overall timings, unless there is something interesting with respect to performance on CPU vs. GPU.


## Experiments

The sections below show how to do a run of either a CPU or GPU experiment. The run number will create a hierarchy under either [data](data) or [monitor](monitor).

### AWS Bare Metal

Deploy the setup. 

```bash
# Choose one
cd tf-aws-gpu
cd tf-aws-cpu
make
```

Experiment orchestration TBA. Note to self - I need to pull the GPU variants of each container for the CPU cluster and re-save the image (currently I pulled CPU variants to test).

### Kubernetes with Operators

For both we can use the same cluster, although for the final experiment we likely want to split them. Undecided.

```bash
# GPU
eksctl create cluster --config-file ./eks-config-gpu-autoscaling.yaml 
eksctl create cluster --config-file ./eks-config-gpu-static.yaml 
aws eks update-kubeconfig --region us-east-1 --name mini-mummi-gpu

# CPU
eksctl create cluster --config-file ./eks-config-cpu-static.yaml 
eksctl create cluster --config-file ./eks-config-cpu-autoscaling.yaml
aws eks update-kubeconfig --region us-east-1 --name mini-mummi
```

```bash
kubectl create namespace monitoring
kubectl apply -f ../event-monitor

# In a different terminal, this will save nodes and collect events.
run_number=1
environ=gpu
mkdir -p ./monitor/state-machine-operator/${environ}/${run_number}
kubectl get nodes -o json > ./monitor/state-machine-operator/${environ}/${run_number}/nodes-$(date +%s).json
kubectl logs -n monitoring $(kubectl get pods -n monitoring -o json | jq -r .items[0].metadata.name) -f |& tee ./monitor/state-machine-operator/${environ}/${run_number}/events-$(date +%s).json
```

#### Mummi Operator


```bash
# 56143b388800a0d48ab3287b497f54beaa20ceaf
git clone https://github.com/converged-computing/mummi-operator
cd mummi-operator
make test-deploy-recreate
```

Run the Experiment:

```bash
kubectl apply -f ./crd/mummi-operator/gpu-mummi.yaml
```

At this point you can save data and /or delete the cluster, or use the same cluster (below).

#### State Machine Operator

Install the operator. Note this requires pushing to a development registry, and you'd need to customize if you don't have access (you likely won't, but I doubt anyone will try to reproduce this).

```bash
# commit
git clone https://github.com/converged-computing/state-machine-operator
cd state-machine-operator
make test-deploy-recreate
```

Run the Experiment:

```bash
kubectl apply -f ./crd/state-machine-operator/gpu-mummi.yaml
```

Delete the GPU cluster

```bash
eksctl delete cluster --config-file ./eks-config-gpu-6.yaml --wait
kubectl delete pods --all --all-namespaces
```

## CPU

### AWS Bare Metal

Deploy the setup. 

```bash
cd tf-aws-cpu
make
```

Experiment orchestration TBA.

### Kubernetes with Operators

```bash
eksctl create cluster --config-file ./eks-config-hpc6a.yaml 
aws eks update-kubeconfig --region us-east-2 --name mini-mummi
```

Install the monitoring tool.

```bash
kubectl create namespace monitoring
kubectl apply -f ../event-monitor

# In a different terminal, this will save nodes and collect events.
run_number=1
environ=cpu
mkdir -p ./monitor/state-machine-operator/${environ}/${run_number}
kubectl get nodes -o json > ./monitor/state-machine-operator/${environ}/${run_number}/nodes-$(date +%s).json
kubectl logs -n monitoring $(kubectl get pods -n monitoring -o json | jq -r .items[0].metadata.name) -f |& tee ./monitor/state-machine-operator/${environ}/${run_number}/events-$(date +%s).json
```

Install the operator

```bash
make test-deploy-recreate
```

Run the Experiment:

```bash
kubectl apply -f ./crd/state-machine-operator/cpu-mummi.yaml
```

```bash
eksctl delete cluster --config-file ./eks-config-hpc6a.yaml --wait
kubectl delete pods --all --all-namespaces
```

Get logs, etc. from the workflow manager.

QUESTION: do we need to save the artifact data?


## Saving data files

Here is how you can interactively count the cganalysis result runs. You'll need to install oras in a container like the wfmanager (or use the mlserver, although we shouldn't interrupt it running):

```bash
# Install oras
VERSION="1.2.2"
curl -LO "https://github.com/oras-project/oras/releases/download/v${VERSION}/oras_${VERSION}_linux_amd64.tar.gz"
mkdir -p oras-install/
tar -zxf oras_${VERSION}_*.tar.gz -C oras-install/
mv oras-install/oras /usr/local/bin/
rm -rf oras_${VERSION}_*.tar.gz oras-install/

# Count
for repo in $(oras repo list --plain-http registry-0.mummi-sample.default.svc.cluster.local:5000); do count=$(oras repo tags --plain-http registry-0.mummi-sample.default.svc.cluster.local:5000/$repo | grep cganalysis | wc -l); if [[ "${count}" != "0" ]]; then echo $count; fi; done
```

I found the easiest thing to do was expose the headless service, and then oras pull to my local machine.

```bash
run_number=1
envion=gpu
#environ=cpu
setup=state-machine-operator
mkdir -p ./data/${setup}/${environ}/${run_number}/
cd ./data/${setup}/${environ}/${run_number}

# In another terminal
kubectl port-forward registry-0 5000:5000
oras repo ls localhost:5000

# Download artifacts organized by structure (repo) and step (tag)
registry=localhost:5000
# registry=registry-0.mummi-sample.default.svc.cluster.local:5000
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
