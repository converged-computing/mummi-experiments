# CPU Node Selector

This portion of the experiment uses the state machine operator to select an ideal node type for the createsims step, and specifically an added feature to allow for [custom properties](https://github.com/converged-computing/state-machine-operator/pull/12). To be consistent in our step, we use the same createsims container that is pre-baked with the analysis and script to process the same gromacs input. We will have the output times for each run, and can choose the instance type based on that. Here are [all the options](https://gist.github.com/vsoch/30803bea5e0bd1b6a0916cef14d54c62) for the cluster autoscaler.

## Docker

In order to make a fair comparison, we need to run the analysis on the same input data. That is done by way of building the container first.

```bash
docker build -t ghcr.io/converged-computing/mummi-experiments:cpu-node-selector .

# And for arm (or better, use the one we already built that is public)
docker buildx build --platform linux/arm64 --build-arg tag=createsims-arm --push -t ghcr.io/converged-computing/mummi-experiments:cpu-node-selector-arm - Dockerfile.arm .

# Run, but be careful if your machine will cough up a fan.
docker run ghcr.io/converged-computing/mummi-experiments:cpu-node-selector
docker push ghcr.io/converged-computing/mummi-experiments:cpu-node-selector
```

## Instance Types

We are going to test CPU, for both ARM and X86. Our one limit is choosing instance types in the same region, which is reasonable (us-east-1). For testing (arm isn't ready yet)

- c7a.4xlarge:
  - 16 vCPU, 32 GiB Memory
  - $0.8211/hour
- m6g.4xlarge
  - 16 vCPU, 32 GiB
  - $0.6160/hour

And for the experiment. Note that some of these are multi-threaded. The difference in specs is OK - my goal was to get an hourly cost close to $3. We would want to see how it performs regardless, they don't have to be totally equal because we care about time/cost.

- c7g.16xlarge (Graviton3/ARM64)
- hpc7g.16xlarge
- c6in.16xlarge (Intel enhanced networking):
  - Note that has enhanced intel networking, unlikely to help
- r7iz.8xlarge
   - Note has Intel high memory and frequency
- m6g.16xlarge
- m6a.16xlarge

See the [configuration YAML files](crd) for the final instances.

## Experiment

Create the cluster. The strategy we use is to have an autoscaling group for each node type we want to test, and then one persistent node where we run services, operators, etc.

```bash
eksctl create cluster --config-file ./crd/eks-config-cpu.yaml
aws eks update-kubeconfig --region us-east-1 --name mini-mummi
```

Install the monitor on the single node that is persistent.

```bash
kubectl create namespace monitoring
kubectl apply -f ../../../event-monitor
environ=cpu-autoscale-0
mkdir -p ./monitor/$environ
kubectl logs -n monitoring $(kubectl get pods -n monitoring -o json | jq -r .items[0].metadata.name) -f |& tee ./monitor/${environ}/events-$(date +%s).json
```

Install the autoscaler, ensure it is running OK, and then install an updated version of the state machine operator.

```bash
kubectl apply -f ./crd/cluster-autoscaler.yaml 
kubectl get pods -n kube-system
# kubectl logs -n kube-system cluster-autoscaler-xxx-xxx
```

Install the state machine operator:

```bash
cd ./state-machine-operator
make test-deploy-recreate
```

At this point we should have what we need for the experiment. The node test should autoscale the cluster to have one node of each type (so the first pod is pending). Run the experiment!

```bash
kubectl apply -f crd/cpu-mummi.yaml
```

To save output:
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

And delete.

```bash
eksctl delete cluster --config-file ../crd/eks-config-cpu.yaml
```
 
