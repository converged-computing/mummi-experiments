# Shape Experiments

Here we are interested in understanding the cost/time tradeoff for different experiment shapes with different allowances for scaling. High level - two types of experiments, each with a parameter sweet, but with different parameters. We have two shapes of jobs:

- low high low
- high low high

And we assume each takes the same amount of time (1 minute). For the experiment with autoscaling, we vary the reaction time of the autoscaler, and allow it to scale up to the maximum set of nodes that could be occupied by all the large jobs at once. For the experiment without autoscaling, we vary the static size of the cluster. For all cases, we compare the actual time spent running the workflow (and cost) with the theoretical best cost (time of running the jobs only). See [notes](notes.md) for more details.



- Autoscaling is on
  - 10 completions
  - low high low (1 4 1), each step 1 minute
  - high low high (4 1 4), each step 1 minute
  - start cluster at 0
  - max size is 40
  - for each experiment, varying reaction time of autoscaler:
    - 30 seconds
    - 1 minute
    - 2 minute

- Autoscaling is off
  - 10 completions
  - low high low (1 4 1), each step 1 minute
  - high low high (4 1 4), each step 1 minute
  - start cluster at sizes:
    - 6 (4s don't fit perfectly, we will get clogging)
    - 8 (should be able to fit sets of 4s)

Start with 6 and 8.

Third experiment to set autoscaling at max size?

20
low high low
2 4 2
high low high
4 2 4

## Overview

I think we should first do experiments that show incremental improvement on different facets of Mummi, with respect to design, and then CPU and GPU (described below). I then think we should choose the best setup and do one more "production" cloud run, maybe with better GPU and larger, and then we can do further looking at the results (or similar).

- Mummi Operator on AWS (represents the old design where the ML server requires an entire node)
   - For each of CPU and GPU (this will assess the tradeoff between the two, assuming limit of cganalysis time)
   - For each of CPU and GPU starting at max size and allowing cluster to downscale
- State Machine Operator on AWS
   - For each of CPU and GPU (this will assess the tradeoff between the two, assuming limit of cganalysis time)
   - For each of CPU and GPU starting at max size and allowing cluster to downscale
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

## Notes

Figuring out which resource type is best would be a second idea/goal.
Idea would be to run each step on different nodes, and choose minimum time.
But for this study we assume each stage has an assigned node type.
Compare potpourri cluster with homogeneous cluster (time and cost)
At the beginning, create N of node type. As the composition of the cluster changes, the autoscaler needs to kick in to provision the node needed.

If time, think of ways to have state machine operator act as node selector.

## Metrics to Collect

 - Timing for events (Kubernetes and via the manager)
 - Total time for experiment (able to calculate cost for entire cluster)
 - Number of outputs for each step produced (e.g., the ML server produces too many)
 - A cool angle would be to use the cost analyzer to run a mock workflow with different designs

## Discussion and Questions

 - The scale for the experiments (see suggestion above)
    - 10 jobs total, 6 starting size and max size allowed to scale to.
    - Need a way to monitor when nodes come up and down (look at Kubernetes event exporter)
    - For node types, GPU and CPU (ask Loic if interesting to test different types of CPU nodes for stages)
 - Run experiments on different clusters
 - Are we stopping cganalysis at 30 minutes (I'm not sure we can afford it if we don't) (Yes)
 - Save all output data (includes timings)
 - Other features I am forgetting? Vertical pod autoscaling?
 - For AWS, I'm having trouble with getting the shared storage working (at least haven't yet). 
 
High level, because we are demonstrating the features moreso than mummi, I think cutting at 30 minutes (or even sooner) is reasonable. I also don't think the output of Mummi is as important as the overall timings, unless there is something interesting with respect to performance on CPU vs. GPU.

## TODO Vanessa

- Come up with random patterns to run.
- Both AMIs need to be rebuilt with my key added to authorized keys, and the data for the model pre-extracted.
  - [ ] GPU needs re-pull and test with flux
  - [ ] Still need to do CPU (tested on older image)
- [ ] Test entire workflow with shared filesystem - deletion is erroneous. Could fall back to flux archive, but not ideal.

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

Will write up next - the containers have been tested a-la-carte on CPU.


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
kubectl apply -f ./crd/state-machine-operator/cpu-mummi.yaml
```

Delete the GPU or CPU cluster

```bash
eksctl delete cluster --config-file ./eks-config-gpu-static.yaml --wait
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
