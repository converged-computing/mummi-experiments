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

```bash
# a88dfe2f98c46896f499a52754eb906fef67eb43 March 5, 2025
git clone https://github.com/converged-computing/state-machine-operator
cd state-machine-operator
```

Install to python:

```bash
sudo python3 -m pip install -e ./python/
```

And you will need the repository root here to create the clusters.

```bash
cd ../
git clone https://github.com/converged-computing/mummi-experiments
```

The containers should already be pulled and data extracted. 
Create the working directory to run

```bash
flux exec -r all mkdir -p /home/ubuntu/workdir
cd /home/ubuntu/workdir
# For some reason flux not on PYTHONPATH
export PYTHONPATH=/usr/lib/python3.10/site-packages
```

Copy the correct set of configs for cpu or gpu

```bash
cp -R ../mummi-experiments/aws-march-2025/state-machine-flux/cpu /home/ubuntu/workdir/local
cp -R ../mummi-experiments/aws-march-2025/state-machine-flux/gpu /home/ubuntu/workdir/local
```

Start the manager to start the workflow. We assume flux is running and we are launching jobs to the system instance.

```bash
state-machine-manager start ./local/cpu/state-machine-workflow.yaml --config-dir=./local/cpu --scheduler flux --filesystem --workdir /home/ubuntu/workdir
```

Note that we will need to unmount the efs filesystem before destroy:

```bash
# TODO test mounting to /home/ubuntu/workdir
sudo umount /mnt/efs

# Haven't tested this yet
flux exec -r all sudo umount /mnt/efs
```

