# Mummi Operator Experiment

> This paradigm is part of the Mummi experiments. Here we are testing using the Mummi Operator, which uses the mlserver and rabbitmq for work.

We won't run autoscaling with the Mummi Operator, the reason being that it doens't make a difference. Traditional mummi has no understanding of when it is done, so jobs continue to be submitted, so autoscaling would not kick in to downscale the cluster. Note that to get the exact digests for containers used, see the final-pods-state.json files in the monitor sub-directories here.

```bash
git clone https://github.com/converged-computing/mummi-experiments
cd ./mummi-experiments/experiments/aws-march-2025/mummi-operator
```

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
# environ=gpu-static
# region=us-east-1
# instance=p3.2xlarge

environ=cpu-static
region=us-east-2
instance=hpc6a.48xlarge

mkdir -p ./monitor/${environ}
kubectl get nodes -o json > ./monitor/${environ}/nodes-$(date +%s).json

# Topology API (only for hpc instance types)
# Note that I was running an a la carte gpu instance in this region, needs to be filtered out
aws ec2 describe-instance-topology --region ${region} --filters Name=instance-type,Values=${instance} > ./monitor/${environ}/topology.json
aws ec2 describe-instances --filters "Name=instance-type,Values=${instance}" --region ${region}  > ./monitor/${environ}/instances.json

kubectl logs -n monitoring $(kubectl get pods -n monitoring -o json | jq -r .items[0].metadata.name) -f |& tee ./monitor/${environ}/events-$(date +%s).json
```

#### Mummi Operator

```bash
# commit used for GPU: 3653b9e8d82d71656fbcf0860d288d1715f4aec3
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
# environ=gpu-static
environ=cpu-static

kubectl logs <container>  > ./monitor/${environ}/<container>.out
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

## Observations and Notes

> cpu-static

Even with the same orchestration, in that the mlserver doesn't use a GPU node, it means we have one more node available to run jobs (because the mlserver goes from needing an entire node, claiming the GPU, to being able to run alongside another pod).

Last cganalysis completed:

- cganalysis-structure-iter00-000000000003-bbrgn   0/1     Completed   0          34m
- cganalysis-structure-iter00-000000000004-cjf54   0/1     Completed   0          34m
- cganalysis-structure-iter00-000000000005-r4wrl   0/1     Completed   0          34m

For some reason the ML server didn't trigger nearly as many structure generations - I don't know why. I might need to do a re-run of one or the other to sanity check. 

> gpu-static

This was fixed to only allow one run and if fail, the job fails. I also remembered there is no actual stopping point, so I needed to stop it when we had 6 completed (I didn't before). Observations:
- It doesn't seem to be nicely orchestrated so that, for example, when createsims jobs are done and cganalysis are underway, it can go back and launch more createsim. It seems to get stuck running cganalysis (submit) until they are complete or change and then go back to the first step.
- cganalysis-structure-iter00-000000000211-kl7cc is the last cganalysis run to finish
- It was inefficient in that 2 more createsims jobs kicked off that we didn't need (and would not finish)
- I realize this approach won't benefit from autoscaling, because there is no intelligence to stop submitting jobs.
- The times aren't saved (or printed) until exit so I shelled it, got the process uid, and did a SIGINT that would allow the class to call `__exit__` and print the result to the log:

```bash
pixi shell
pixi add htop
# get wfmanager process
htop
kill -s SIGINT <process_id>
```

And make sure to select the python. Then save the log with times.

> gpu-static-fail-0

## Run 1

> This was an erroneous run that turned into a test run, but provided valuable insights.

This run was erroneous in that jobs were allowed to retry. What happened is that one createsims job retried 5 times and ran without error on the 5th, but it isn't clear the simulation would ever finish. The last one was allowed to run up to 80 minutes (no limit was set). Since no limit was set, manual intervention was required to clean it up and allow another createsim to fill the slot. This delayed the entire orchestration, because instead of sending 2 jobs down the line, we only had one, and a slot was taken up. Essentially we were wasting an additional node. I allowed this to continue because this run represents what is likely a real-world example of what might happen with one unexpected event, and I wanted it for comparison with a fixed variant of this, where jobs are not allowed to retry, and a limit of 45 minutes is set.

- Watching rabbitmq, it also has several restarts / fails, it's risky running a service.
- The MLServer, even when controlled and not creating too many samples, is still taking up an entire node and creating samples that won't be used. It also freezes, and then the beginning of the pipeline stops and new samples are not generated.
- When the MLServer froze and I needed to restart it (delete the pod to be re-created) it had to pull freshly to the node.

Overall, this run shows problems that arise when orchestration is not well connected, and services (that can fail or otherwise not function correctly) are involved. The jobs would eventually run, but since it is one big loop that is depending on other jobs finishing, and since the orchestration was thrown off with the number of components running to match resources, it seemed to result in this erroneous state. I can't comment beyond that. I stopped it around 8 completed cganalysis because I forgot it needs a manual stop.

## Cleanup

```bash
# GPU
kubectl delete -f crd/gpu-mummi.yaml
eksctl delete cluster --config-file ../eks-config-gpu-static.yaml --wait

# CPU
kubectl delete -f crd/cpu-mummi.yaml
eksctl create cluster --config-file ../eks-config-cpu-static.yaml --wait
```

