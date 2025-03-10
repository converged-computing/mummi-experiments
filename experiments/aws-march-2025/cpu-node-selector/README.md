# CPU Node Selector

This portion of the experiment uses the state machine operator to select an ideal node type for the createsims step, and specifically an added feature to allow for [custom properties](https://github.com/converged-computing/state-machine-operator/pull/12). To be consistent in our step, we use the same createsims container that is pre-baked with the analysis and script to process the same gromacs input. We will have the output times for each run, and can choose the instance type based on that.

## Docker

In order to make a fair comparison, we need to run the analysis on the same input data. That is done by way of building the container first.

```bash
docker build -t ghcr.io/converged-computing/mummi-experiments:cpu-node-selector .

# Run, but be careful if your machine will cough up a fan.
docker run ghcr.io/converged-computing/mummi-experiments:cpu-node-selector
docker push ghcr.io/converged-computing/mummi-experiments:cpu-node-selector
```

I'm working on the ability to select a node next, and I'll also need to figure out how to make a cluster with different node types. If we require, for example, all of the same node type to start, it's not clear if we should do a design that is horizontal (running the same type in the same state machines over time) or vertical (running as the same step in multiple state machines so the cluster does not need to scale). 

## Instance Types

We are going to test CPU, for both ARM and X86. Our one limit is choosing instance types in the same region, which is reasonable (us-east-1). For testing (and I'll remove the ARM when it isn't ready yet):

- c7g.4xlarge (Graviton3/ARM64)
  - 16 vCPU, 32 GiB Memory
  - $0.58 / hour
- c7a.4xlarge:
  - 16 vCPU, 32 GiB Memory
  - $0.8211/hour
- m6g.4xlarge
  - 16 vCPU, 32 GiB
  - $0.6160/hour

And for the experiment. Note that some of these are multi-threaded. The difference in specs is OK - my goal was to get an hourly cost close to $3. We would want to see how it performs regardless, they don't have to be totally equal because we care about time/cost.

- c7g.16xlarge (Graviton3/ARM64): 
  - 64 vCPU, 128 GiB Memory
  - $2.32/hour
- hpc6a.48xlarge:
  - 96 cores
  - $2.88/hour
- c6in.4xlarge (Intel enhanced networking):
  - 48 vCPU 96 Memory GiB
  - Note that has enhanced intel networking, unlikely to help
  - $2.722 /hour
- r7iz.8xlarge
   - Note has Intel high memory and frequency
   - 32 vCPU, 256 Memory GiB
   - $2.976/hour
- m6g.4xlarge
   - 16 vCPU, 64 Memory GiB
   - $0.6160/hour

## Testing

Let's test using the autoscaler, first with two cheap node types:

```bash
eksctl create cluster --config-file eks-config-cpu-autoscaling-test.yaml
aws eks update-kubeconfig --region us-east-1 --name mini-mummi
```

We want to see if the events exported includes node data.

```bash
kubectl create namespace monitoring
kubectl apply -f ../../../event-monitor
environ=cpu-autoscale
mkdir -p ./monitor/$environ
kubectl logs -n monitoring $(kubectl get pods -n monitoring -o json | jq -r .items[0].metadata.name) -f |& tee ./monitor/${environ}/events-$(date +%s).json
```

Install the autoscaler, ensure it is running OK, and then install an updated version of the state machine operator.

```bash
kubectl apply -f ./crd/cluster-autoscaler-test.yaml 
kubectl get pods -n kube-system
kubectl logs -n kube-system cluster-autoscaler-xxx-xxx
```

Install the state machine operator:

```bash
cd ./state-machine-operator
make test-deploy-recreate
```

At this point we should have what we need for the experiment. The node test should autoscale the cluster to have one node of each type (so the first pod is pending). Run the experiment!

```bash
kubectl apply -f crd/cpu-mummi-test.yaml
```

I want to test this with spot too. Delete.

```bash
eksctl delete cluster --config-file eks-config-cpu-autoscaling-test.yaml --wait
```

Test with spot!

```bash
eksctl create cluster --config-file eks-config-cpu-autoscaling-spot-test.yaml
aws eks update-kubeconfig --region us-east-2 --name mini-mummi
```


## Original Notes

- Figuring out which resource type is best would be a second idea/goal.
- Idea would be to run each step on different nodes, and choose minimum time.
- But for this study we assume each stage has an assigned node type.
- Compare potpourri cluster with homogeneous cluster (time and cost)
- At the beginning, create N of node type. As the composition of the cluster changes, the autoscaler needs to kick in to provision the node needed!

If time, think of ways to have state machine operator act as node selector (this study!)
