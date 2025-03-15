# State Machine Flux

The sections below show how to do a run of either a CPU or GPU experiment. 

## AWS Bare Metal

Deploy the setup.  This will be moved to a different directory (organized with data, etc.) when run.

```bash
# Choose one
cd tf-aws-gpu
cd tf-aws-cpu-arm
make
```

Then get the lead instance IP and shell in. 
And note to delete, I had trouble with make destroy and the autoscaling group. I needed to delete both the storage and autoscaling group manually.

```console
# Storage
aws delete-file-system --file-system-id mummi-gpu-efs --region us-east-1
aws delete-file-system --file-system-id mummi-cpu-efs --region us-east-2

# Autoscaling
aws autoscaling delete-auto-scaling-group --force-delete --auto-scaling-group-name flux-autoscaling-group --region us-east-1
aws autoscaling delete-auto-scaling-group --force-delete --auto-scaling-group-name flux-autoscaling-group --region us-east-2
```

### Setup

We need to clone and install the state machine operator.

- cpu runs started at 3:30pm March 15, 2025

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

```
sudo mount -t efs fs-05c3a94e6db80a87a.efs.us-east-1.amazonaws.com /home/ubuntu/workdir
flux exec -r all -x 0 sudo mount -t efs fs-05c3a94e6db80a87a.efs.us-east-1.amazonaws.com /home/ubuntu/workdir
```

Then touched a filed and tested:

```bash
touch /mnt/efs/file.txt
flux exec -r all sudo mkdir -p /mnt/efs
flux exec -r all sudo mount -t efs fs-05c3a94e6db80a87a.efs.us-east-1.amazonaws.com /mnt/efs
flux exec -r all sudo chown -R ubuntu /mnt/efs
flux exec -r all ls /mnt/efs/
mkdir -p /mnt/efs/iter-1
cd /mnt/efs/iter-1
```

Start the manager to start the workflow. We assume flux is running and we are launching jobs to the system instance.

```bash
# I used screen first, and shelled into the instance from another terminal to look at the queue.
# screen
export PYTHONPATH=/usr/lib/python3.10/site-packages
state-machine-manager start ../local/state-machine-workflow.yaml --config-dir=../local --scheduler flux --filesystem --workdir /mnt/efs/iter-1
```

We do the above for three iterations - it's nice that we can run three experiments on the same cluster (since we don't need to account for pulling). After, we need to save the iteration data with artifacts. Here is what I did on one node:

```bash
mkdir -p /home/ubuntu/iter-1 /home/ubuntu/iter-2 /home/ubuntu/iter-3
cp -R /mnt/efs/iter-1/structure_* /home/ubuntu/iter-1/
cp -R /mnt/efs/iter-2/structure_* /home/ubuntu/iter-2/
cp -R /mnt/efs/iter-3/structure_* /home/ubuntu/iter-3/
oras push ghcr.io/converged-computing/mummi-experiments:cpu-arm-iter-1 /home/ubuntu/iter-1/
oras push ghcr.io/converged-computing/mummi-experiments:cpu-arm-iter-2 /home/ubuntu/iter-2/
oras push ghcr.io/converged-computing/mummi-experiments:cpu-arm-iter-3 /home/ubuntu/iter-3/
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
