# CPU/GPU Node Selector for cganalysis

See background and rationale in [cpu-node-selector](../cpu-node-selector). This is the equivalent for cganalysis. We are going to be testing:

- gpu
- arm
- cpu (amd64)

## Docker

In order to make a fair comparison, we need to run the analysis on the same input data. That is done by way of building the container first.

```bash
docker build -t ghcr.io/converged-computing/mummi-experiments:node-selector-cganalysis-cpu .
docker push ghcr.io/converged-computing/mummi-experiments:node-selector-cganalysis-cpu

docker build -f Dockerfile.gpu -t ghcr.io/converged-computing/mummi-experiments:node-selector-cganalysis-gpu .
docker push ghcr.io/converged-computing/mummi-experiments:node-selector-cganalysis-gpu

docker buildx build --platform linux/arm64 --build-arg tag=cganalysis-arm --load -t ghcr.io/converged-computing/mummi-experiments:node-selector-cganalysis-arm -f Dockerfile.arm .
docker push ghcr.io/converged-computing/mummi-experiments:node-selector-cganalysis-arm
```

## Experiment

Create the cluster. The strategy we use is to have an autoscaling group for each node type we want to test, and then one persistent node where we run services, operators, etc.

```bash
eksctl create cluster --config-file ./crd/eks-config-cpu.yaml
eksctl create cluster --config-file ./crd/eks-config-cpu-spot.yaml
aws eks update-kubeconfig --region us-east-1 --name mini-mummi

# This is for hpc6a (in a different zone)
eksctl create cluster --config-file ./crd/eks-config-hpc6a.yaml
aws eks update-kubeconfig --region us-east-2 --name mini-mummi
```

Install the autoscaler, ensure it is running OK, and then install an updated version of the state machine operator. Make sure that it is running.

```bash
kubectl apply -f ./crd/cluster-autoscaler.yaml 
kubectl apply -f crd/cluster-autoscaler-hpc6a.yaml 
kubectl get pods -n kube-system
# kubectl logs -n kube-system cluster-autoscaler-xxx-xxx
```

Install the state machine operator:

```bash
git clone https://github.com/converged-computing/state-machine-operator
kubectl apply -f examples/dist/state-machine-operator-dev.yaml 
```

At this point we should have what we need for the experiment. The node test should autoscale the cluster to have one node of each type (so the first pod is pending). Run the experiment!

```bash
# Run separately for each of arm and amd to be conservative
kubectl apply -f crd/cpu-mummi.yaml
kubectl apply -f crd/cpu-mummi-hpc6a.yaml
```

For spot, get the spot instance scores so we can compare to our ability to get instances.

```bash
mkdir -p spot-scores
cd spot-scores
for instance in "c6in.12xlarge" "c7a.12xlarge" "c7g.12xlarge" "hpc7g.16xlarge" "m6a.16xlarge" "m6g.16xlarge" "r7iz.8xlarge"
do
  aws ec2 get-spot-placement-scores --instance-types $instance --region us-east-2 --target-capacity=3 > spot-scores-$instance.json
done
instance="hpc6a.48xlarge"
aws ec2 get-spot-placement-scores --instance-types $instance --region us-east-1 --target-capacity=3 > spot-scores-$instance.json
```

To save output files, I would copy them from the manager, and then get the artifacts from oras.

```
mkdir monitor/$environ
cd monitor $environ
kubectl cp <manager>:/opt/logs .
```

Then oras pull to your local machine:

```bash
# In another terminal
kubectl port-forward registry-0 5000:5000
oras repo ls localhost:5000

environ=arm64
mkdir -p ./monitor/$environ
cd ./monitor/$environ
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

I then moved each log into its corresponding directory.

And delete.

```bash
eksctl delete cluster --config-file ./crd/eks-config-cpu.yaml --wait
eksctl delete cluster --config-file ./crd/eks-config-cpu-spot.yaml --wait
eksctl delete cluster --config-file ./crd/eks-config-hpc6a.yaml --wait
```

## Notes:

- For spot instances:
  - We could not get hpc7g or hpc6a
  - We lost one r7iz-8xlarge at 7.5 minutes
  - m6a we lost one early on, and one right at the end before the final output save.
  - m6g we got them fairly quickly and lost all 3 in ~100 seconds
