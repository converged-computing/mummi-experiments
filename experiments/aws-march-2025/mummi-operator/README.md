# Mummi Operator Experiment

> This paradigm is part of the Mummi experiments. Here we are testing using the Mummi Operator, which uses the mlserver and rabbitmq for work.

We won't run autoscaling with the Mummi Operator, the reason being that it doesn't make a difference. Traditional mummi has no understanding of when it is done, so jobs continue to be submitted, so autoscaling would not kick in to downscale the cluster. Note that to get the exact digests for containers used, see the final-pods-state.json files in the monitor sub-directories here.

```bash
git clone https://github.com/converged-computing/mummi-experiments
cd ./mummi-experiments/experiments/aws-march-2025/mummi-operator
```
Final results:

 - XXXX is final for CPU
 - gpu-static-1 is final for GPU

## Experiments

There will be two experiments - one for GPU and one for CPU.

```bash
# GPU
eksctl create cluster --config-file ../eks-config-gpu-static.yaml
aws eks update-kubeconfig --region us-east-1 --name mini-mummi-gpu

# CPU
eksctl create cluster --config-file ../eks-config-cpu-static.yaml 
aws eks update-kubeconfig --region us-east-2 --name mini-mummi
```

```bash
kubectl create namespace monitoring
kubectl apply -f ../../../event-monitor

# In a different terminal, this will save nodes and collect events.
# environ=cpu-static-0
# region=us-east-2
# instance=hpc6a.48xlarge

environ=gpu-static-1
region=us-east-1
instance=p3.2xlarge

mkdir -p ./monitor/${environ}
kubectl get nodes -o json > ./monitor/${environ}/nodes-$(date +%s).json

# Topology API (only for hpc instance types)
# Note that I was running an a la carte gpu instance in this region, needs to be filtered out
# aws ec2 describe-instance-topology --region ${region} --filters Name=instance-type,Values=${instance} > ./monitor/${environ}/topology.json
aws ec2 describe-instances --filters "Name=instance-type,Values=${instance}" --region ${region}  > ./monitor/${environ}/instances.json

kubectl logs -n monitoring $(kubectl get pods -n monitoring -o json | jq -r .items[0].metadata.name) -f |& tee ./monitor/${environ}/events-$(date +%s).json
```

#### Mummi Operator

This is private, so we install from a local build.

```bash
# commit used for GPU and CPU final runs: cd88384394fc601a474551aa4c4adfb573eb3131
git clone https://github.com/converged-computing/mummi-operator
cd mummi-operator
make test-deploy-recreate
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
environ=gpu-static-1
# environ=cpu-static-0

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
kill -s SIGINT 364
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

- For the GPU runs, one of the createsims ran the entire duration of the study, meaning there was only one node for createsims. It increased the time by 1.5x likely.

Also see [notes](notes.md) from testing runs.


