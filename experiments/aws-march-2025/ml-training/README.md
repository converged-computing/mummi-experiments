# Machine Learning Model Training

This experiment aims to emulate a training run for a machine learning model. We use pytorch resnet as a proxy for a model that can put out a metric of goodness, which the state machine operator can read and react to, stopping training when a particular threshold is reached..

## Experiments

We will run these on the 1 GPU instances, 4 total.

```bash
eksctl create cluster --config-file ./eks-config-gpu.yaml
aws eks update-kubeconfig --region us-east-1 --name mummi-ml-gpu
```

#### State Machine Operator

```bash
# From github.com/converged-computing/state-machine-operator
make test-deploy-recreate
```

Save nodes, etc.

```bash
mkdir -p ./data
kubectl get nodes -o json > ./data/nodes-$(date +%s).json
```

And install JobSet

```bash
kubectl apply --server-side -f https://github.com/kubernetes-sigs/jobset/releases/download/v0.4.0/manifests.yaml
```

Run the Experiment. 

```bash
kubectl apply -f state-machine.yaml
kubectl logs state-machine-manager-67cdc565b-gdr4q > ./data/manager.out
kubectl cp shape-manager-xxx:/workflow-times.json ./data/workflow-times.json
kubectl cp shape-manager-xxx:/cluster-nodes.json ./data/cluster-nodes.json
kubectl get jobs -o json > ./data/jobs.json
kubectl get pods -o json > ./data/pods.json
kubectl cp state-machine-manager-xxx<>:/opt/logs ./data/logs
kubectl get pods -o wide > ./data/pods-final-state.txt
```


## Saving the model

I found the easiest thing to do was expose the headless service, and then oras pull to my local machine.

```bash
# In another terminal
kubectl port-forward registry-0 5000:5000
oras repo ls localhost:5000

mkdir data/model
cd ./data/model
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

When you are done, to clean up:

```bash
kubectl delete jobs --all
kubectl delete jobset --all
kubectl delete pods --all --all-namespaces
eksctl delete cluster --config-file ./eks-config-gpu.yaml --wait
```

