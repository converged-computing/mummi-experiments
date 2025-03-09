#!/bin/bash

set -o pipefail

# docker build -t ghcr.io/converged-computing/mummi-experiments:cpu-node-selector
# docker push ghcr.io/converged-computing/mummi-experiments:cpu-node-selector

jobid=structure_099868581
outpath=/tmp/out

. ~/.bash_profile
MUMMI_APP=/opt/clones/mummi-ras MUMMI_ROOT=$MUMMI_APP
MUMMI_RESOURCES=/opt/clones/mummi_resources
export MUMMI_ROOT MUMMI_APP MUMMI_RESOURCES
export OMP_NUM_THREADS=6
locpath=/tmp/workdir
mkdir -p ${outpath}; cd ${locpath}
mummi_createsim \
  --fstype simple \
  --patch ${jobid} \
  --inpath $(pwd) \
  --outpath $outpath \
  --outlocal $locpath \
  --logpath $locpath \
  --loglevel 2 \
  --gromacs gmx \
  --mpi "gmx mdrun" \
  --mini \
  --mdrunopt " -ntmpi 1 -ntomp $OMP_NUM_THREADS -pin off"
