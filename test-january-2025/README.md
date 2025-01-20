# Test Experiments

This test will be for two base experiments with the following criteria.

1. Either CPU (hpc6a.48xlarge, $2.88/hour on demand) or GPU nodes (p3.2xlarge, $3.06/hour on demand).
2. Event exporting with [kubernetes-event-exporter](https://github.com/resmoio/kubernetes-event-exporter)
3. 6 Nodes total.
4. A total of 6 total runs (cganalysis).
5. We will time from when nodes come up to when the last run finishes.

For CPU nodes, we will ask for 94/96 cores per task. For GPU, since the GPU has 1/node, that specification on the request will handle the scheduling topology. For setup for both:

```bash
# run 1 used commit used is 9328b81ca06ce5585fc1b137fed7e4b0db8fb3e1 from January 17, 2025 with manual  tweaks
# run 2 used commit e5100fd49bdd6ff9c6f5745b6c2fd5dea4458031
git clone https://github.com/converged-computing/mummi-operator
cd mummi-operator
```

And you will need the repository root here to create the clusters, etc.

```bash
git clone https://github.com/converged-computing/mummi-experiments
cd ./mummi-experiments/test-january-2025
```

## Experiments

The sections below show how to do a run of either a CPU or GPU experiment. The run number will create a hierarchy under either [data](data) or [monitor](monitor).

## 1. Create Cluster

```bash
# GPU cluster
eksctl create cluster --config-file ./eks-config-gpu-6.yaml
aws eks update-kubeconfig --region us-east-1 --name mini-mummi-gpu

# CPU Cluster
eksctl create cluster --config-file ./eks-config-hpc6a.yaml
aws eks update-kubeconfig --region us-east-2 --name mini-mummi
```

<details>

<summary>EKS Cluster Creation</summary>

First GPU cluster (1)

```console
2025-01-19 11:29:57 [ℹ]  eksctl version 0.189.0-dev+c9afc4260.2024-08-27T16:08:34Z
2025-01-19 11:29:57 [ℹ]  using region us-east-1
2025-01-19 11:29:57 [ℹ]  subnets for us-east-1b - public:192.168.0.0/19 private:192.168.64.0/19
2025-01-19 11:29:57 [ℹ]  subnets for us-east-1c - public:192.168.32.0/19 private:192.168.96.0/19
2025-01-19 11:29:57 [ℹ]  nodegroup "workers" will use "" [AmazonLinux2/1.27]
2025-01-19 11:29:57 [ℹ]  using SSH public key "/home/vanessa/.ssh/id_eks.pub" as "eksctl-mini-mummi-gpu-nodegroup-workers-4e:93:d9:47:eb:81:3e:4f:1b:e0:44:ac:af:c6:ac:b3" 
2025-01-19 11:29:57 [ℹ]  using Kubernetes version 1.27
2025-01-19 11:29:57 [ℹ]  creating EKS cluster "mini-mummi-gpu" in "us-east-1" region with managed nodes
2025-01-19 11:29:57 [ℹ]  1 nodegroup (workers) was included (based on the include/exclude rules)
2025-01-19 11:29:57 [ℹ]  will create a CloudFormation stack for cluster itself and 0 nodegroup stack(s)
2025-01-19 11:29:57 [ℹ]  will create a CloudFormation stack for cluster itself and 1 managed nodegroup stack(s)
2025-01-19 11:29:57 [ℹ]  if you encounter any issues, check CloudFormation console or try 'eksctl utils describe-stacks --region=us-east-1 --cluster=mini-mummi-gpu'
2025-01-19 11:29:57 [ℹ]  Kubernetes API endpoint access will use default of {publicAccess=true, privateAccess=false} for cluster "mini-mummi-gpu" in "us-east-1"
2025-01-19 11:29:57 [ℹ]  CloudWatch logging will not be enabled for cluster "mini-mummi-gpu" in "us-east-1"
2025-01-19 11:29:57 [ℹ]  you can enable it with 'eksctl utils update-cluster-logging --enable-types={SPECIFY-YOUR-LOG-TYPES-HERE (e.g. all)} --region=us-east-1 --cluster=mini-mummi-gpu'
2025-01-19 11:29:57 [ℹ]  default addons vpc-cni, kube-proxy, coredns were not specified, will install them as EKS addons
2025-01-19 11:29:57 [ℹ]  
2 sequential tasks: { create cluster control plane "mini-mummi-gpu", 
    2 sequential sub-tasks: { 
        2 sequential sub-tasks: { 
            1 task: { create addons },
            wait for control plane to become ready,
        },
        create managed nodegroup "workers",
    } 
}
2025-01-19 11:29:57 [ℹ]  building cluster stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 11:29:58 [ℹ]  deploying stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 11:30:28 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 11:30:58 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 11:31:58 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 11:32:59 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 11:33:59 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 11:34:59 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 11:36:00 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 11:37:00 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 11:38:00 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 11:39:00 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 11:40:01 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 11:41:01 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 11:42:01 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 11:43:02 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 11:43:04 [!]  recommended policies were found for "vpc-cni" addon, but since OIDC is disabled on the cluster, eksctl cannot configure the requested permissions; the recommended way to provide IAM permissions for "vpc-cni" addon is via pod identity associations; after addon creation is completed, add all recommended policies to the config file, under `addon.PodIdentityAssociations`, and run `eksctl update addon`
2025-01-19 11:43:04 [ℹ]  creating addon
2025-01-19 11:43:04 [ℹ]  successfully created addon
2025-01-19 11:43:04 [ℹ]  creating addon
2025-01-19 11:43:05 [ℹ]  successfully created addon
2025-01-19 11:43:06 [ℹ]  creating addon
2025-01-19 11:43:06 [ℹ]  successfully created addon
2025-01-19 11:45:07 [ℹ]  building managed nodegroup stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 11:45:08 [ℹ]  deploying stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 11:45:08 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 11:45:38 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 11:46:21 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 11:47:27 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 11:48:16 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 11:48:16 [ℹ]  waiting for the control plane to become ready
2025-01-19 11:48:16 [✔]  saved kubeconfig as "/home/vanessa/.kube/config"
2025-01-19 11:48:16 [ℹ]  1 task: { install Nvidia device plugin }
2025-01-19 11:48:17 [ℹ]  created "kube-system:DaemonSet.apps/nvidia-device-plugin-daemonset"
2025-01-19 11:48:17 [ℹ]  as you are using the EKS-Optimized Accelerated AMI with a GPU-enabled instance type, the Nvidia Kubernetes device plugin was automatically installed.
	to skip installing it, use --install-nvidia-plugin=false.
2025-01-19 11:48:17 [✔]  all EKS cluster resources for "mini-mummi-gpu" have been created
2025-01-19 11:48:17 [✔]  created 0 nodegroup(s) in cluster "mini-mummi-gpu"
2025-01-19 11:48:17 [ℹ]  nodegroup "workers" has 6 node(s)
2025-01-19 11:48:17 [ℹ]  node "ip-192-168-2-2.ec2.internal" is ready
2025-01-19 11:48:17 [ℹ]  node "ip-192-168-2-98.ec2.internal" is ready
2025-01-19 11:48:17 [ℹ]  node "ip-192-168-20-132.ec2.internal" is ready
2025-01-19 11:48:17 [ℹ]  node "ip-192-168-30-39.ec2.internal" is ready
2025-01-19 11:48:17 [ℹ]  node "ip-192-168-7-95.ec2.internal" is ready
2025-01-19 11:48:17 [ℹ]  node "ip-192-168-9-100.ec2.internal" is ready
2025-01-19 11:48:17 [ℹ]  waiting for at least 6 node(s) to become ready in "workers"
2025-01-19 11:48:17 [ℹ]  nodegroup "workers" has 6 node(s)
2025-01-19 11:48:17 [ℹ]  node "ip-192-168-2-2.ec2.internal" is ready
2025-01-19 11:48:17 [ℹ]  node "ip-192-168-2-98.ec2.internal" is ready
2025-01-19 11:48:17 [ℹ]  node "ip-192-168-20-132.ec2.internal" is ready
2025-01-19 11:48:17 [ℹ]  node "ip-192-168-30-39.ec2.internal" is ready
2025-01-19 11:48:17 [ℹ]  node "ip-192-168-7-95.ec2.internal" is ready
2025-01-19 11:48:17 [ℹ]  node "ip-192-168-9-100.ec2.internal" is ready
2025-01-19 11:48:17 [✔]  created 1 managed nodegroup(s) in cluster "mini-mummi-gpu"
2025-01-19 11:48:17 [✖]  getting Kubernetes version on EKS cluster: error running `kubectl version`: exit status 1 (check 'kubectl version')
2025-01-19 11:48:17 [ℹ]  cluster should be functional despite missing (or misconfigured) client binaries
2025-01-19 11:48:17 [✔]  EKS cluster "mini-mummi-gpu" in "us-east-1" region is ready
```

Second GPU cluster (2)

```console
2025-01-19 17:23:08 [ℹ]  eksctl version 0.189.0-dev+c9afc4260.2024-08-27T16:08:34Z
2025-01-19 17:23:08 [ℹ]  using region us-east-1
2025-01-19 17:23:08 [ℹ]  subnets for us-east-1b - public:192.168.0.0/19 private:192.168.64.0/19
2025-01-19 17:23:08 [ℹ]  subnets for us-east-1c - public:192.168.32.0/19 private:192.168.96.0/19
2025-01-19 17:23:08 [ℹ]  nodegroup "workers" will use "" [AmazonLinux2/1.27]
2025-01-19 17:23:08 [ℹ]  using SSH public key "/home/vanessa/.ssh/id_eks.pub" as "eksctl-mini-mummi-gpu-nodegroup-workers-4e:93:d9:47:eb:81:3e:4f:1b:e0:44:ac:af:c6:ac:b3" 
2025-01-19 17:23:09 [ℹ]  using Kubernetes version 1.27
2025-01-19 17:23:09 [ℹ]  creating EKS cluster "mini-mummi-gpu" in "us-east-1" region with managed nodes
2025-01-19 17:23:09 [ℹ]  1 nodegroup (workers) was included (based on the include/exclude rules)
2025-01-19 17:23:09 [ℹ]  will create a CloudFormation stack for cluster itself and 0 nodegroup stack(s)
2025-01-19 17:23:09 [ℹ]  will create a CloudFormation stack for cluster itself and 1 managed nodegroup stack(s)
2025-01-19 17:23:09 [ℹ]  if you encounter any issues, check CloudFormation console or try 'eksctl utils describe-stacks --region=us-east-1 --cluster=mini-mummi-gpu'
2025-01-19 17:23:09 [ℹ]  Kubernetes API endpoint access will use default of {publicAccess=true, privateAccess=false} for cluster "mini-mummi-gpu" in "us-east-1"
2025-01-19 17:23:09 [ℹ]  CloudWatch logging will not be enabled for cluster "mini-mummi-gpu" in "us-east-1"
2025-01-19 17:23:09 [ℹ]  you can enable it with 'eksctl utils update-cluster-logging --enable-types={SPECIFY-YOUR-LOG-TYPES-HERE (e.g. all)} --region=us-east-1 --cluster=mini-mummi-gpu'
2025-01-19 17:23:09 [ℹ]  default addons vpc-cni, kube-proxy, coredns were not specified, will install them as EKS addons
2025-01-19 17:23:09 [ℹ]  
2 sequential tasks: { create cluster control plane "mini-mummi-gpu", 
    2 sequential sub-tasks: { 
        2 sequential sub-tasks: { 
            1 task: { create addons },
            wait for control plane to become ready,
        },
        create managed nodegroup "workers",
    } 
}
2025-01-19 17:23:09 [ℹ]  building cluster stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 17:23:09 [ℹ]  deploying stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 17:23:39 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 17:24:09 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 17:25:10 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 17:26:10 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 17:27:10 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 17:28:11 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 17:29:11 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 17:30:11 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 17:31:11 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 17:32:12 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 17:33:12 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 17:34:12 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 17:34:14 [!]  recommended policies were found for "vpc-cni" addon, but since OIDC is disabled on the cluster, eksctl cannot configure the requested permissions; the recommended way to provide IAM permissions for "vpc-cni" addon is via pod identity associations; after addon creation is completed, add all recommended policies to the config file, under `addon.PodIdentityAssociations`, and run `eksctl update addon`
2025-01-19 17:34:14 [ℹ]  creating addon
2025-01-19 17:34:15 [ℹ]  successfully created addon
2025-01-19 17:34:15 [ℹ]  creating addon
2025-01-19 17:34:16 [ℹ]  successfully created addon
2025-01-19 17:34:16 [ℹ]  creating addon
2025-01-19 17:34:17 [ℹ]  successfully created addon
2025-01-19 17:36:18 [ℹ]  building managed nodegroup stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 17:36:19 [ℹ]  deploying stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 17:36:19 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 17:36:49 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 17:37:21 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 17:38:48 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 17:39:50 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 17:39:50 [ℹ]  waiting for the control plane to become ready
2025-01-19 17:39:50 [✔]  saved kubeconfig as "/home/vanessa/.kube/config"
2025-01-19 17:39:50 [ℹ]  1 task: { install Nvidia device plugin }
2025-01-19 17:39:51 [ℹ]  created "kube-system:DaemonSet.apps/nvidia-device-plugin-daemonset"
2025-01-19 17:39:51 [ℹ]  as you are using the EKS-Optimized Accelerated AMI with a GPU-enabled instance type, the Nvidia Kubernetes device plugin was automatically installed.
        to skip installing it, use --install-nvidia-plugin=false.
2025-01-19 17:39:51 [✔]  all EKS cluster resources for "mini-mummi-gpu" have been created
2025-01-19 17:39:51 [✔]  created 0 nodegroup(s) in cluster "mini-mummi-gpu"
2025-01-19 17:39:52 [ℹ]  nodegroup "workers" has 6 node(s)
2025-01-19 17:39:52 [ℹ]  node "ip-192-168-1-106.ec2.internal" is ready
2025-01-19 17:39:52 [ℹ]  node "ip-192-168-10-242.ec2.internal" is ready
2025-01-19 17:39:52 [ℹ]  node "ip-192-168-11-149.ec2.internal" is ready
2025-01-19 17:39:52 [ℹ]  node "ip-192-168-2-14.ec2.internal" is ready
2025-01-19 17:39:52 [ℹ]  node "ip-192-168-28-70.ec2.internal" is ready
2025-01-19 17:39:52 [ℹ]  node "ip-192-168-29-184.ec2.internal" is ready
2025-01-19 17:39:52 [ℹ]  waiting for at least 6 node(s) to become ready in "workers"
2025-01-19 17:39:52 [ℹ]  nodegroup "workers" has 6 node(s)
2025-01-19 17:39:52 [ℹ]  node "ip-192-168-1-106.ec2.internal" is ready
2025-01-19 17:39:52 [ℹ]  node "ip-192-168-10-242.ec2.internal" is ready
2025-01-19 17:39:52 [ℹ]  node "ip-192-168-11-149.ec2.internal" is ready
2025-01-19 17:39:52 [ℹ]  node "ip-192-168-2-14.ec2.internal" is ready
2025-01-19 17:39:52 [ℹ]  node "ip-192-168-28-70.ec2.internal" is ready
2025-01-19 17:39:52 [ℹ]  node "ip-192-168-29-184.ec2.internal" is ready
2025-01-19 17:39:52 [✔]  created 1 managed nodegroup(s) in cluster "mini-mummi-gpu"
2025-01-19 17:39:52 [✖]  getting Kubernetes version on EKS cluster: error running `kubectl version`: exit status 1 (check 'kubectl version')
2025-01-19 17:39:52 [ℹ]  cluster should be functional despite missing (or misconfigured) client binaries
2025-01-19 17:39:52 [✔]  EKS cluster "mini-mummi-gpu" in "us-east-1" region is ready
```

First CPU cluster (1)

```console
2025-01-19 19:42:30 [ℹ]  eksctl version 0.189.0-dev+c9afc4260.2024-08-27T16:08:34Z
2025-01-19 19:42:30 [ℹ]  using region us-east-2
2025-01-19 19:42:30 [ℹ]  subnets for us-east-2b - public:192.168.0.0/19 private:192.168.64.0/19
2025-01-19 19:42:30 [ℹ]  subnets for us-east-2c - public:192.168.32.0/19 private:192.168.96.0/19
2025-01-19 19:42:30 [ℹ]  nodegroup "workers" will use "" [AmazonLinux2/1.27]
2025-01-19 19:42:30 [ℹ]  using SSH public key "/home/vanessa/.ssh/id_eks.pub" as "eksctl-mini-mummi-nodegroup-workers-4e:93:d9:47:eb:81:3e:4f:1b:e0:44:ac:af:c6:ac:b3" 
2025-01-19 19:42:30 [ℹ]  using Kubernetes version 1.27
2025-01-19 19:42:30 [ℹ]  creating EKS cluster "mini-mummi" in "us-east-2" region with managed nodes
2025-01-19 19:42:30 [ℹ]  1 nodegroup (workers) was included (based on the include/exclude rules)
2025-01-19 19:42:30 [ℹ]  will create a CloudFormation stack for cluster itself and 0 nodegroup stack(s)
2025-01-19 19:42:30 [ℹ]  will create a CloudFormation stack for cluster itself and 1 managed nodegroup stack(s)
2025-01-19 19:42:30 [ℹ]  if you encounter any issues, check CloudFormation console or try 'eksctl utils describe-stacks --region=us-east-2 --cluster=mini-mummi'
2025-01-19 19:42:30 [ℹ]  Kubernetes API endpoint access will use default of {publicAccess=true, privateAccess=false} for cluster "mini-mummi" in "us-east-2"
2025-01-19 19:42:30 [ℹ]  CloudWatch logging will not be enabled for cluster "mini-mummi" in "us-east-2"
2025-01-19 19:42:30 [ℹ]  you can enable it with 'eksctl utils update-cluster-logging --enable-types={SPECIFY-YOUR-LOG-TYPES-HERE (e.g. all)} --region=us-east-2 --cluster=mini-mummi'
2025-01-19 19:42:30 [ℹ]  default addons vpc-cni, kube-proxy, coredns were not specified, will install them as EKS addons
2025-01-19 19:42:30 [ℹ]  
2 sequential tasks: { create cluster control plane "mini-mummi", 
    2 sequential sub-tasks: { 
        2 sequential sub-tasks: { 
            1 task: { create addons },
            wait for control plane to become ready,
        },
        create managed nodegroup "workers",
    } 
}
2025-01-19 19:42:30 [ℹ]  building cluster stack "eksctl-mini-mummi-cluster"
2025-01-19 19:42:31 [ℹ]  deploying stack "eksctl-mini-mummi-cluster"
2025-01-19 19:43:01 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-cluster"
2025-01-19 19:43:31 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-cluster"
2025-01-19 19:44:31 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-cluster"
2025-01-19 19:45:32 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-cluster"
2025-01-19 19:46:32 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-cluster"
2025-01-19 19:47:32 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-cluster"
2025-01-19 19:48:32 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-cluster"
2025-01-19 19:49:33 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-cluster"
2025-01-19 19:50:33 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-cluster"
2025-01-19 19:51:33 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-cluster"
2025-01-19 19:52:33 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-cluster"
2025-01-19 19:53:34 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-cluster"
2025-01-19 19:54:34 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-cluster"
2025-01-19 19:54:36 [!]  recommended policies were found for "vpc-cni" addon, but since OIDC is disabled on the cluster, eksctl cannot configure the requested permissions; the recommended way to provide IAM permissions for "vpc-cni" addon is via pod identity associations; after addon creation is completed, add all recommended policies to the config file, under `addon.PodIdentityAssociations`, and run `eksctl update addon`
2025-01-19 19:54:36 [ℹ]  creating addon
2025-01-19 19:54:36 [ℹ]  successfully created addon
2025-01-19 19:54:36 [ℹ]  creating addon
2025-01-19 19:54:37 [ℹ]  successfully created addon
2025-01-19 19:54:37 [ℹ]  creating addon
2025-01-19 19:54:38 [ℹ]  successfully created addon
2025-01-19 19:56:39 [ℹ]  building managed nodegroup stack "eksctl-mini-mummi-nodegroup-workers"
2025-01-19 19:56:39 [ℹ]  skipping us-east-2c from selection because it doesn't support the following instance type(s): hpc6a.48xlarge
2025-01-19 19:56:40 [ℹ]  deploying stack "eksctl-mini-mummi-nodegroup-workers"
2025-01-19 19:56:40 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-nodegroup-workers"
2025-01-19 19:57:10 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-nodegroup-workers"
2025-01-19 19:57:54 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-nodegroup-workers"
2025-01-19 19:58:35 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-nodegroup-workers"
2025-01-19 20:00:33 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-nodegroup-workers"
2025-01-19 20:00:33 [ℹ]  waiting for the control plane to become ready
2025-01-19 20:00:33 [✔]  saved kubeconfig as "/home/vanessa/.kube/config"
2025-01-19 20:00:33 [ℹ]  no tasks
2025-01-19 20:00:33 [✔]  all EKS cluster resources for "mini-mummi" have been created
2025-01-19 20:00:33 [✔]  created 0 nodegroup(s) in cluster "mini-mummi"
2025-01-19 20:00:33 [ℹ]  nodegroup "workers" has 6 node(s)
2025-01-19 20:00:33 [ℹ]  node "ip-192-168-15-59.us-east-2.compute.internal" is ready
2025-01-19 20:00:33 [ℹ]  node "ip-192-168-19-200.us-east-2.compute.internal" is ready
2025-01-19 20:00:33 [ℹ]  node "ip-192-168-29-184.us-east-2.compute.internal" is ready
2025-01-19 20:00:33 [ℹ]  node "ip-192-168-30-119.us-east-2.compute.internal" is ready
2025-01-19 20:00:33 [ℹ]  node "ip-192-168-30-43.us-east-2.compute.internal" is ready
2025-01-19 20:00:33 [ℹ]  node "ip-192-168-5-207.us-east-2.compute.internal" is ready
2025-01-19 20:00:33 [ℹ]  waiting for at least 6 node(s) to become ready in "workers"
2025-01-19 20:00:34 [ℹ]  nodegroup "workers" has 6 node(s)
2025-01-19 20:00:34 [ℹ]  node "ip-192-168-15-59.us-east-2.compute.internal" is ready
2025-01-19 20:00:34 [ℹ]  node "ip-192-168-19-200.us-east-2.compute.internal" is ready
2025-01-19 20:00:34 [ℹ]  node "ip-192-168-29-184.us-east-2.compute.internal" is ready
2025-01-19 20:00:34 [ℹ]  node "ip-192-168-30-119.us-east-2.compute.internal" is ready
2025-01-19 20:00:34 [ℹ]  node "ip-192-168-30-43.us-east-2.compute.internal" is ready
2025-01-19 20:00:34 [ℹ]  node "ip-192-168-5-207.us-east-2.compute.internal" is ready
2025-01-19 20:00:34 [✔]  created 1 managed nodegroup(s) in cluster "mini-mummi"
2025-01-19 20:00:34 [✖]  getting Kubernetes version on EKS cluster: error running `kubectl version`: exit status 1 (check 'kubectl version')
2025-01-19 20:00:34 [ℹ]  cluster should be functional despite missing (or misconfigured) client binaries
2025-01-19 20:00:34 [✔]  EKS cluster "mini-mummi" in "us-east-2" region is ready
```

</details>

Install the monitoring tool.

```bash
kubectl create namespace monitoring
kubectl apply -f ../event-monitor

# In a different terminal, this will save nodes and collect events.
run_number=1
# environ=gpu
environ=cpu
mkdir -p ./monitor/${environ}/${run_number}
kubectl get nodes -o json > ./monitor/${environ}/${run_number}/nodes-$(date +%s).json
kubectl logs -n monitoring $(kubectl get pods -n monitoring -o json | jq -r .items[0].metadata.name) -f |& tee ./monitor/${environ}/${run_number}/events-$(date +%s).json
```

## 2. Install the Operator

```bash
make test-deploy-recreate
```

## 3. Run the Experiment

I didn't hit any issues with the workflow manager and rabbitmq when I started it manually.

```bash
# createsims takes about ~15-17 minutes
# cganalysis is hard coded to stop at 30 minutes, but can go up to 34/35
# timeout for rabbitmq is set to 3 hours
kubectl apply -f gpu-mummi.yaml

# createsims takes about 21-25 minutes
# cganalysis still hard coded to stop (probably doesn't get as far)
# timeout is the same
kubectl apply -f cpu-mummi.yaml
```

Note that I chose to run the workflow manager interactively, meaning I shelled in and manually started it. 

```bash
kubectl exec -it mummi-sample-wfmanager-64d87ddb87-44mkd -- bash
pixi shell
cp /mummi_operator/kubernetes_start.sh .
/bin/bash kubernetes_start.sh
```

I did this in case I wanted to stop it and tweak any of the configuration files. From that point you'll need to monitor the jobs and stop (saving data first) when the final cganalysis is done. The events tool will collect container pulling times. When we improve upon the setup, we will have this stopping point more clearly defined.

## 4. Save data files

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
#envion=gpu
environ=cpu
mkdir -p ./data/${environ}/${run_number}/
cd ./data/${environ}/${run_number}

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

## 5. Cleanup

This will stop the event exporter from running, etc.

```bash
# Delete the GPU cluster
eksctl delete cluster --config-file ./eks-config-gpu-6.yaml --wait
kubectl delete pods --all --all-namespaces

# Delete the CPU cluster
eksctl delete cluster --config-file ./eks-config-hpc6a.yaml --wait
kubectl delete pods --all --all-namespaces
```

<details>

<summary>Cluster Deletion</summary>

First GPU run

```console
2025-01-19 14:44:05 [ℹ]  deleting EKS cluster "mini-mummi-gpu"
2025-01-19 14:44:06 [ℹ]  will drain 0 unmanaged nodegroup(s) in cluster "mini-mummi-gpu"
2025-01-19 14:44:06 [ℹ]  starting parallel draining, max in-flight of 1
2025-01-19 14:44:06 [✖]  failed to acquire semaphore while waiting for all routines to finish: context canceled
2025-01-19 14:44:07 [ℹ]  deleted 0 Fargate profile(s)
2025-01-19 14:44:08 [✔]  kubeconfig has been updated
2025-01-19 14:44:08 [ℹ]  cleaning up AWS load balancers created by Kubernetes objects of Kind Service or Ingress
2025-01-19 14:44:10 [ℹ]  
2 sequential tasks: { delete nodegroup "workers", delete cluster control plane "mini-mummi-gpu" 
}
2025-01-19 14:44:10 [ℹ]  will delete stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 14:44:10 [ℹ]  waiting for stack "eksctl-mini-mummi-gpu-nodegroup-workers" to get deleted
2025-01-19 14:44:10 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 14:44:40 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 14:45:25 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 14:46:26 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 14:47:34 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 14:49:25 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 14:50:31 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 14:52:11 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 14:54:10 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 14:55:06 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 14:56:55 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 14:58:14 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 14:58:58 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 15:00:51 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 15:00:51 [ℹ]  will delete stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 15:00:51 [ℹ]  waiting for stack "eksctl-mini-mummi-gpu-cluster" to get deleted
2025-01-19 15:00:51 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 15:01:21 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 15:02:18 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 15:03:16 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 15:03:16 [✔]  all cluster resources were deleted
```

Second GPU run:

```console
2025-01-19 19:35:07 [ℹ]  deleting EKS cluster "mini-mummi-gpu"
2025-01-19 19:35:08 [ℹ]  will drain 0 unmanaged nodegroup(s) in cluster "mini-mummi-gpu"
2025-01-19 19:35:08 [ℹ]  starting parallel draining, max in-flight of 1
2025-01-19 19:35:08 [✖]  failed to acquire semaphore while waiting for all routines to finish: context canceled
2025-01-19 19:35:08 [ℹ]  deleted 0 Fargate profile(s)
2025-01-19 19:35:09 [✔]  kubeconfig has been updated
2025-01-19 19:35:09 [ℹ]  cleaning up AWS load balancers created by Kubernetes objects of Kind Service or Ingress
2025-01-19 19:35:11 [ℹ]  
2 sequential tasks: { delete nodegroup "workers", delete cluster control plane "mini-mummi-gpu" 
}
2025-01-19 19:35:11 [ℹ]  will delete stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 19:35:11 [ℹ]  waiting for stack "eksctl-mini-mummi-gpu-nodegroup-workers" to get deleted
2025-01-19 19:35:11 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"

^[[A2025-01-19 19:35:41 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 19:36:14 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 19:37:29 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"

2025-01-19 19:38:55 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 19:40:04 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 19:41:05 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 19:42:51 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 19:43:52 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 19:44:44 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 19:45:38 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 19:46:48 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 19:48:18 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-nodegroup-workers"
2025-01-19 19:48:19 [ℹ]  will delete stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 19:48:19 [ℹ]  waiting for stack "eksctl-mini-mummi-gpu-cluster" to get deleted
2025-01-19 19:48:19 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 19:48:49 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 19:49:40 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 19:50:42 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-gpu-cluster"
2025-01-19 19:50:42 [✔]  all cluster resources were deleted
```

First CPU Run

```console
2025-01-19 22:17:20 [ℹ]  deleting EKS cluster "mini-mummi"
2025-01-19 22:17:20 [ℹ]  will drain 0 unmanaged nodegroup(s) in cluster "mini-mummi"
2025-01-19 22:17:20 [ℹ]  starting parallel draining, max in-flight of 1
2025-01-19 22:17:20 [✖]  failed to acquire semaphore while waiting for all routines to finish: context canceled
2025-01-19 22:17:21 [ℹ]  deleted 0 Fargate profile(s)
2025-01-19 22:17:22 [✔]  kubeconfig has been updated
2025-01-19 22:17:22 [ℹ]  cleaning up AWS load balancers created by Kubernetes objects of Kind Service or Ingress
2025-01-19 22:17:23 [ℹ]  
2 sequential tasks: { delete nodegroup "workers", delete cluster control plane "mini-mummi" 
}
2025-01-19 22:17:23 [ℹ]  will delete stack "eksctl-mini-mummi-nodegroup-workers"
2025-01-19 22:17:23 [ℹ]  waiting for stack "eksctl-mini-mummi-nodegroup-workers" to get deleted
2025-01-19 22:17:23 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-nodegroup-workers"
2025-01-19 22:17:54 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-nodegroup-workers"
2025-01-19 22:18:46 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-nodegroup-workers"
2025-01-19 22:19:58 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-nodegroup-workers"
2025-01-19 22:21:58 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-nodegroup-workers"
2025-01-19 22:22:45 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-nodegroup-workers"
2025-01-19 22:22:45 [ℹ]  will delete stack "eksctl-mini-mummi-cluster"
2025-01-19 22:22:45 [ℹ]  waiting for stack "eksctl-mini-mummi-cluster" to get deleted
2025-01-19 22:22:45 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-cluster"
2025-01-19 22:23:16 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-cluster"
2025-01-19 22:23:59 [ℹ]  waiting for CloudFormation stack "eksctl-mini-mummi-cluster"
2025-01-19 22:24:00 [✔]  all cluster resources were deleted
```

</details>


## Notes

- We shouldn't be generating samples like we do - e.g., I am watching it churn out starting simulations but the containers for the first 2 haven't been pulled yet. The iteration almost doesn't matter - before we had a ton generated under one iteration, and now we have just 3. The difference is that we are checking the other steps more frequently (e.g., for createsim to finish).
