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

- TODO: Account for saving of output for failed jobs too (a pro and con)!
