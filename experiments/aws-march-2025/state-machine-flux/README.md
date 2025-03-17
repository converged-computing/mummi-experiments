# State Machine Flux

The sections below show how to do a run of either a CPU or GPU experiment. 

## Experiments

### Pulling Times

Since we will have the containers pulled to the image to save time, we still need a metric of pulling time
for containers, because the operator (Kubernetes) experiments all include one pull per container per node. We will do this with our final analysis containers on each respective instance type and save times.

#### p3.2xlarge

Each of these was done on the final AMI used for experiments.

```bash
# On your host with credentials: (username is AWS)
# aws ecr get-login-password --region us-east-1
# export SINGULARITY_DOCKER_USERNAME=AWS
# export SINGULARITY_DOCKER_PASSWORD=<token>

mkdir /home/ubuntu/containers
cd /home/ubuntu/containers
mkdir -p times
container=docker://633731392008.dkr.ecr.us-east-1.amazonaws.com/mini-mummi
for iter in $(seq 1 3)
  do
  echo "Pulling mlrunner"
  { time singularity pull $container:mlrunner-gpu 2> pull.stderr ; } 2> ./times/mlrunner-pull-time-$iter.txt
  echo "Pulling createsims"
  { time singularity pull $container:createsims-gpu 2> pull.stderr ; } 2> ./times/createsime-pull-time-$iter.txt
  echo "Pulling cganalysis"
  { time singularity pull $container:cganalsis-gpu 2> pull.stderr ; } 2> ./times/cganalysis-pull-time-$iter.txt
  singularity cache clean --force
  rm -rf *.sif
done
```

#### hpc7g.16xlarge

```bash
# On your host with credentials: (username is AWS)
# aws ecr get-login-password --region us-east-1
# export SINGULARITY_DOCKER_USERNAME=AWS
# export SINGULARITY_DOCKER_PASSWORD=<token>

mkdir /home/ubuntu/containers
cd /home/ubuntu/containers
mkdir -p times
container=docker://633731392008.dkr.ecr.us-east-1.amazonaws.com/mini-mummi
for iter in $(seq 1 3)
  do
  echo "Pulling mlrunner"
  { time singularity pull $container:mlrunner-arm-singularity 2> pull.stderr ; } 2> ./times/mlrunner-pull-time-$iter.txt
  echo "Pulling createsims"
  { time singularity pull $container:createsims-arm 2> pull.stderr ; } 2> ./times/createsime-pull-time-$iter.txt
  echo "Pulling cganalysis"
  { time singularity pull $container:cganalsis-arm 2> pull.stderr ; } 2> ./times/cganalysis-pull-time-$iter.txt
  singularity cache clean --force
  rm -rf *.sif
done
```

These times are in [results/container-pulls](results/container-pulls).

### AWS Bare Metal

Deploy the setup.  This will be moved to a different directory (organized with data, etc.) when run.

```bash
# Choose one
cd tf-aws-gpu
cd tf-aws-cpu-arm
make
```

Then get the lead instance IP and shell in. 
And note to delete, I had trouble with make destroy and the autoscaling group. I needed to delete both the storage and autoscaling group manually. For EFS use the UI, and for autoscaling you can also do:

```console
# Autoscaling
aws autoscaling delete-auto-scaling-group --force-delete --auto-scaling-group-name flux-autoscaling-group --region us-east-1
aws autoscaling delete-auto-scaling-group --force-delete --auto-scaling-group-name flux-autoscaling-group --region us-east-2
```

### Setup

We need to clone and install the state machine operator.

```bash
# a30e92ca345fca6575a99b0e4f3ad74a07d92766 March 14, 2025
git clone https://github.com/converged-computing/state-machine-operator
cd state-machine-operator
sudo python3 -m pip install -e ./python/
```

And you will need the repository root here to create the clusters.

```bash
cd ../
git clone https://github.com/converged-computing/mummi-experiments
```

The containers should already be pulled and data extracted.  The working directory should be created and mounted across nodes.

```bash
export PYTHONPATH=/usr/lib/python3.10/site-packages
```

Copy the correct set of configs for cpu or gpu

```bash
cp -R ../mummi-experiments/aws-march-2025/state-machine-flux/cpu /home/ubuntu/workdir/local
cp -R ../mummi-experiments/aws-march-2025/state-machine-flux/gpu /home/ubuntu/workdir/local
```
In practice I found the efs filesystem failed mounting, so I looked at /var/log/cloud-init-output.out to get the name, then did:

```bash
flux exec -r all sudo mkdir -p /mnt/efs
# Get the identifier from /var/log/cloud-init-output.log
flux exec -r all sudo mount -t efs fs-0e0083fb904f24d6e.efs.us-east-1.amazonaws.com /mnt/efs
flux exec -r all sudo chown -R ubuntu /mnt/efs
touch /mnt/efs/file.txt
# You should see N copies of file.txt (the same file)
flux exec -r all ls /mnt/efs/
mkdir -p /mnt/efs/iter-1
cd /mnt/efs/iter-1
```

For the GPU instances, if we need in the start script:

```bash
flux exec -r all flux module unload sched-simple
flux exec -r all flux module load /usr/lib/flux/modules/sched-fluxion-resource.so 
flux exec -r all flux module load /usr/lib/flux/modules/sched-fluxion-qmanager.so 
sudo modprobe nvidia-uvm
```

Note this seems to only need to be loaded on the lead broker node.
Between iterations we need to clear the queue and remove the old files.

```bash
flux job purge --age-limit=0 --force
rm -rf /home/ubuntu/iter-2
```

Start the manager to start the workflow. We assume flux is running and we are launching jobs to the system instance.

```bash
# I used screen first, and shelled into the instance from another terminal to look at the queue.
# screen
export PYTHONPATH=/usr/lib/python3.10/site-packages
state-machine-manager start ../local/state-machine-workflow.yaml --config-dir=../local --scheduler flux --filesystem --workdir /mnt/efs/iter-3
```

We do the above for three iterations - it's nice that we can run three experiments on the same cluster (since we don't need to account for pulling). After, we need to save the iteration data with artifacts. Here is what I did on one node:

```bash
iter=1
mkdir -p /home/ubuntu/iter-$iter
cp -R /mnt/efs/iter-$iter/structure_* /home/ubuntu/iter-$iter/
cp /mnt/efs/iter-$iter/workflow-times.json /home/ubuntu/iter-$iter/
```

For each I also saved complete flux metadata from the queue:

```bash
# When they are done:
cd /home/ubuntu/iter-$iter
mkdir -p ./logs
flux jobs -a > final-queue-state.txt
output=/home/ubuntu/iter-$iter/logs
for jobid in $(flux jobs -a --json | jq -r .jobs[].id)
  do
    # Get the job name and structure
    step_name=$(flux job info $jobid jobspec | jq -r ".attributes.user.app")    
    structure=$(flux job info $jobid jobspec | jq -r ".attributes.user.jobname")    
    outfile=$output/${structure}-${step_name}-${jobid}.out
    flux job attach $jobid &> $outfile
    echo "START OF JOBSPEC" >> $outfile
    flux job info $jobid jobspec >> $outfile
    echo "START OF EVENTLOG" >> $outfile
    flux job info $jobid guest.exec.eventlog >> $outfile
done
```

Login to oras then push result.

```bash
oras login ghcr.io
```

```bash
cd /home/ubuntu/iter-$iter/
oras push ghcr.io/converged-computing/mummi-experiments:gpu-arm-iter-$iter .
oras push ghcr.io/converged-computing/mummi-experiments:cpu-arm-iter-$iter .
```

Note that we will need to unmount the efs filesystem before destroy:

```bash
flux exec -r all sudo umount /mnt/efs
```

Then exit and:

```bash
make destroy
```

If you have trouble (it seems to be spinning on the autoscaling group) delete the efs filesystem and the autoscaling group in the AWS console.

## Analysis

### Output Files

Since this is using the state machine operator, we don't see any issue with excess and total jobs. There are only excess for steps that needed to be re-run. Unlike Kubernetes where these outputs (in the current implementation) aren't saved (pushed to the registry) the persistent filesystem means that we keep all result files.

```console
Experiment Job Counts (completed with results)
    experiment         job count iteration
0   cpu-static    mlsample    11         1
1   cpu-static   createsim    10         1
2   cpu-static  cganalysis    10         1
3   cpu-static    mlsample    10         3
4   cpu-static   createsim    10         3
5   cpu-static  cganalysis    10         3
6   cpu-static    mlsample    10         2
7   cpu-static   createsim    10         2
8   cpu-static  cganalysis    10         2
9   gpu-static    mlsample    11         1
10  gpu-static   createsim    10         1
11  gpu-static  cganalysis    10         1
12  gpu-static    mlsample    10         3
13  gpu-static   createsim    10         3
14  gpu-static  cganalysis    10         3
15  gpu-static    mlsample    10         2
16  gpu-static   createsim    10         2
17  gpu-static  cganalysis    10         2
```

Thus, the excess reflects failures of a step.

```
Excess Completed
    experiment         job count iteration
0   cpu-static    mlsample     1         1
1   cpu-static   createsim     0         1
2   cpu-static  cganalysis     0         1
3   cpu-static    mlsample     0         3
4   cpu-static   createsim     0         3
5   cpu-static  cganalysis     0         3
6   cpu-static    mlsample     0         2
7   cpu-static   createsim     0         2
8   cpu-static  cganalysis     0         2
9   gpu-static    mlsample     1         1
10  gpu-static   createsim     0         1
11  gpu-static  cganalysis     0         1
12  gpu-static    mlsample     0         3
13  gpu-static   createsim     0         3
14  gpu-static  cganalysis     0         3
15  gpu-static    mlsample     0         2
16  gpu-static   createsim     0         2
17  gpu-static  cganalysis     0         2
```

### Pulling Times

Singularity containers take a lot longer to pull than docker because they require generating the SIF.
Note that the experiments do NOT include these times, so the face value assessment is not a fair one.

![results/processed/pull_times_by_experiment](results/processed/pull_times_by_experiment)


### Function Times

Like the other results, the CPU ARM outperforms the GPU setup.

![results/processed/function_times_by_experiment.png](results/processed/function_times_by_experiment.png)

These are total summed timed across the experiment for different events.

```bash
experiment  global              iteration
cpu-static  cganalysis_success  1            17978.735104
                                2            17947.466616
                                3            16474.328401
            createsim_failure   1               36.650442
            createsim_success   1             5105.182107
                                2             5087.932331
                                3             4967.893207
            mlrunner_failure    2                7.613389
            mlrunner_success    1              607.525203
                                2              115.811255
                                3              100.458604
            workflow_complete   1             4745.525153
                                2             4644.108295
                                3             4584.863189
gpu-static  cganalysis_success  1            17983.249766
                                2            17881.616295
                                3            17882.139705
            createsim_failure   1               74.436712
            createsim_success   1             7047.289262
                                2             6979.106718
                                3             6936.831313
            mlrunner_success    1              293.894655
                                2              161.889552
                                3              161.450266
            workflow_complete   1             5059.972774
                                2             5044.751449
                                3             5017.005129
Name: duration, dtype: object
```

And these are mean times per single run, across iterations. Here we can glimpse at the workflow total time too.

![results/processed/workflow_manager_times.png](results/processed/workflow_manager_times.png)
![results/processed/workflow_total_time.png](results/processed/workflow_total_time.png)

```
experiment  global            
cpu-static  cganalysis_success    1746.684337
            createsim_failure       36.650442
            createsim_success      505.366921
            mlrunner_failure         7.613389
            mlrunner_success        26.574034
            workflow_complete     4658.165546
gpu-static  cganalysis_success    1791.566859
            createsim_failure       74.436712
            createsim_success      698.774243
            mlrunner_success        19.910789
            workflow_complete     5040.576451
```

### Costs

The costs are similar to the other environments (Kubernetes).

![results/processed/workflow_total_cost.png](results/processed/workflow_total_cost.png)

Here is without pull:

```console
{
    "cpu-static": {
        "1": 13.31119805528283,
        "3": 12.860541245763303,
        "2": 13.02672376871109
    },
    "gpu-static": {
        "1": 25.80586114633083,
        "3": 25.58672615962029,
        "2": 25.7282323892355
    }
}
```

And here is with pull:

```console
{
    "cpu-static": {
        "1": 15.149376265282832,
        "3": 14.663595245763302,
        "2": 14.87129457371109
    },
    "gpu-static": {
        "1": 37.950113746330835,
        "3": 38.099775059620285,
        "2": 38.8857529892355
    }
}
```
