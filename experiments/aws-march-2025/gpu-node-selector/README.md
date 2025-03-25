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
  
  
## Results

```
          instance simulation_ns               sample       spot       instance_name  hourly_cost  half_hour_cost cost_per_simulation_ns
18    c7g-16xlarge          53.5  structure_006217962       spot   c7g-16xlarge-spot       0.5415         0.27075               0.005061
8     c7g-16xlarge          52.5  structure_080531946       spot   c7g-16xlarge-spot       0.5415         0.27075               0.005157
14    c7g-16xlarge          52.5  structure_027786779       spot   c7g-16xlarge-spot       0.5415         0.27075               0.005157
6       p3-2xlarge          30.5  structure_084840146       spot     p3-2xlarge-spot       0.3760         0.18800               0.006164
5     c7a-12xlarge          51.5  structure_067366513       spot   c7a-12xlarge-spot       0.6458         0.32290                0.00627
12    c7a-12xlarge          46.5  structure_042686490       spot   c7a-12xlarge-spot       0.6458         0.32290               0.006944
15    c7a-12xlarge          45.5  structure_062152093       spot   c7a-12xlarge-spot       0.6458         0.32290               0.007097
11      p3-2xlarge          19.5  structure_077031477       spot     p3-2xlarge-spot       0.3760         0.18800               0.009641
7       p3-2xlarge          19.5  structure_077236396       spot     p3-2xlarge-spot       0.3760         0.18800               0.009641
3   hpc7g-16xlarge          53.5  structure_042030664  on-demand      hpc7g-16xlarge       1.6830         0.84150               0.015729
1   hpc7g-16xlarge          52.5  structure_030303311  on-demand      hpc7g-16xlarge       1.6830         0.84150               0.016029
0   hpc7g-16xlarge          52.0  structure_032102085  on-demand      hpc7g-16xlarge       1.6830         0.84150               0.016183
2   hpc7g-16xlarge          52.0  structure_055438499  on-demand      hpc7g-16xlarge       1.6830         0.84150               0.016183
17   c6in-12xlarge          22.0  structure_050113487       spot  c6in-12xlarge-spot       0.8272         0.41360                 0.0188
30    c7g-16xlarge          53.5  structure_018976077  on-demand        c7g-16xlarge       2.3200         1.16000               0.021682
37    c7g-16xlarge          53.5  structure_011469773  on-demand        c7g-16xlarge       2.3200         1.16000               0.021682
23    c7g-16xlarge          52.0  structure_080296043  on-demand        c7g-16xlarge       2.3200         1.16000               0.022308
9    c6in-12xlarge          17.5  structure_064668606       spot  c6in-12xlarge-spot       0.8272         0.41360               0.023634
25    c7a-12xlarge          52.0  structure_080296043  on-demand        c7a-12xlarge       2.4630         1.23150               0.023683
10   c6in-12xlarge          17.0  structure_037634390       spot  c6in-12xlarge-spot       0.8272         0.41360               0.024329
32    c7a-12xlarge          50.5  structure_018976077  on-demand        c7a-12xlarge       2.4630         1.23150               0.024386
39    c7a-12xlarge          50.0  structure_011469773  on-demand        c7a-12xlarge       2.4630         1.23150                0.02463
16    m6a-16xlarge          17.0  structure_040099301       spot   m6a-16xlarge-spot       0.8596         0.42980               0.025282
13    r7iz-8xlarge          14.0  structure_034117895       spot   r7iz-8xlarge-spot       0.7677         0.38385               0.027418
4     r7iz-8xlarge          14.0  structure_099352644       spot   r7iz-8xlarge-spot       0.7677         0.38385               0.027418
29    m6g-16xlarge          40.5  structure_018976077  on-demand        m6g-16xlarge       2.4640         1.23200                0.03042
36    m6g-16xlarge          40.0  structure_011469773  on-demand        m6g-16xlarge       2.4640         1.23200                 0.0308
22    m6g-16xlarge          40.0  structure_080296043  on-demand        m6g-16xlarge       2.4640         1.23200                 0.0308
43      p3-2xlarge          32.5  structure_002428053  on-demand          p3-2xlarge       3.0600         1.53000               0.047077
28      p3-2xlarge          31.0  structure_024332431  on-demand          p3-2xlarge       3.0600         1.53000               0.049355
35  hpc6a-48xlarge          24.0  structure_021755152  on-demand      hpc6a-48xlarge       2.8800         1.44000                   0.06
21  hpc6a-48xlarge          24.0  structure_014136731  on-demand      hpc6a-48xlarge       2.8800         1.44000                   0.06
42  hpc6a-48xlarge          23.5  structure_090721860  on-demand      hpc6a-48xlarge       2.8800         1.44000               0.061277
38   c6in-12xlarge          22.0  structure_011469773  on-demand       c6in-12xlarge       2.7220         1.36100               0.061864
20      p3-2xlarge          20.0  structure_063157840  on-demand          p3-2xlarge       3.0600         1.53000                 0.0765
41    m6a-16xlarge          18.0  structure_011469773  on-demand        m6a-16xlarge       2.7650         1.38250               0.076806
31   c6in-12xlarge          17.5  structure_018976077  on-demand       c6in-12xlarge       2.7220         1.36100               0.077771
19      p3-2xlarge          19.5  structure_040591829  on-demand          p3-2xlarge       3.0600         1.53000               0.078462
24   c6in-12xlarge          17.0  structure_080296043  on-demand       c6in-12xlarge       2.7220         1.36100               0.080059
40    r7iz-8xlarge          18.0  structure_011469773  on-demand        r7iz-8xlarge       2.9760         1.48800               0.082667
26    r7iz-8xlarge          14.5  structure_080296043  on-demand        r7iz-8xlarge       2.9760         1.48800               0.102621
33    r7iz-8xlarge          14.5  structure_018976077  on-demand        r7iz-8xlarge       2.9760         1.48800               0.102621
27    m6a-16xlarge           4.5  structure_080296043  on-demand        m6a-16xlarge       2.7650         1.38250               0.307222
34    m6a-16xlarge           4.5  structure_018976077  on-demand        m6a-16xlarge       2.7650         1.38250               0.307222

```
