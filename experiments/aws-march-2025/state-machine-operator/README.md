# State Machine Operator Experiment

> This paradigm is part of the Mummi experiments. Here we are testing using the State Machine Operator, which uses a state machine and removes some of the persistent services in favor of Kubernetes events

```bash
git clone https://github.com/converged-computing/mummi-experiments
cd ./mummi-experiments/experiments/aws-march-2025/state-machine-operator
```

Final results:

 - gpu-static-1
 - cpu-static-1

## Experiments

There will be four experiments - one for GPU and one for CPU, and each with and without autoscaling.

> TODO for GPU autoscaling add --node-labels k8s.amazonaws.com/accelerator=<gpu-type> so we need a second file. Also need to think about general design.

```bash
# GPU
eksctl create cluster --config-file ../eks-config-gpu-static.yaml
eksctl create cluster --asg-access --config-file ../eks-config-gpu-autoscaling.yaml
aws eks update-kubeconfig --region us-east-1 --name mini-mummi-gpu

# CPU
eksctl create cluster --config-file ../eks-config-cpu-static.yaml 
eksctl create cluster --asg-access --config-file ../eks-config-cpu-autoscaling.yaml
aws eks update-kubeconfig --region us-east-2 --name mini-mummi
```

```bash
kubectl create namespace monitoring
kubectl apply -f ../../../event-monitor

# In a different terminal, this will save nodes and collect events.
environ=cpu-static-1
region=us-east-2
instance=hpc6a.48xlarge

# environ=gpu-static-1
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
# commit for cpu and gpu
# f0e880c46277e49c5b301f92bee93e58e127addc
git clone https://github.com/converged-computing/state-machine-operator
cd state-machine-operator
make test-deploy-recreate
```

Run the Experiment. Note that since the resources here are going directly to Kubernetes, we ask for exactly what we want each job to have.

```bash
kubectl apply -f ./crd/gpu-mummi.yaml
kubectl apply -f ./crd/cpu-mummi.yaml
```

## Saving data files

When the workflow is complete, we can save the state, etc. First, get output for the different components. For each of the manager and registry, do:

```bash
# In a different terminal, this will save nodes and collect events.
# environ=gpu-static-1
environ=cpu-static-1

#kubectl logs <container>  > ./monitor/${environ}/<container>.out
kubectl get pods -o wide > ./monitor/${environ}/final-pods-state.txt
kubectl get pods -o json > ./monitor/${environ}/final-pods-state.json

# Copy times from the manager
kubectl cp mummi-manager-86ddd95986-5gctw:/workflow-times.json workflow-times.json
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

```bash
# GPU
kubectl delete -f crd/gpu-mummi.yaml
eksctl delete cluster --config-file ../eks-config-gpu-static.yaml --wait

# CPU
kubectl delete -f crd/cpu-mummi.yaml
eksctl delete cluster --config-file ../eks-config-cpu-static.yaml --wait
```

## Notes

- The GPU mlrunner had an error, but it simply created another state machine to replace it.
- The state machine operator uses GROMACS instead of GROMACS_PARTS to support feedback better, they are functionally equivalent
- It's hard to say (this is subjective) but it seems like there are more errors when gromacs is running on CPU.
