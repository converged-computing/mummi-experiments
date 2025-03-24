#!/bin/bash

set -o pipefail

# Flag for gpus?
usegpu=${1:-yes}
if [ "${usegpu}" == "no" ]; then
  echo "This run does not use GPU";
  nogpu="--no-gpu"
else
  nogpu=""
  echo "This run uses GPU";
fi

jobid=structure_099868581
outpath=/tmp/out

. ~/.bash_profile
MUMMI_APP=/opt/clones/mummi-ras MUMMI_ROOT=$MUMMI_APP
MUMMI_RESOURCES=/opt/clones/mummi_resources
export MUMMI_ROOT MUMMI_APP MUMMI_RESOURCES
export OMP_NUM_THREADS=$(nproc)

# This is already created with data
locpath=/tmp/workdir
mkdir -p ${outpath}; cd ${locpath}
export OMPI_COMM_WORLD_RANK=1

echo ">> simname  = $jobid"
echo ">> outpath  = $outpath"
echo ">> registry = $registry"
echo ">> locpath  = $locpath"
echo ">> gmx      =" $(command -v gmx)
echo ">> pwd      =" $(pwd)
echo ">> hostname =" $(hostname)

cd ${outpath}
outfile=${outpath}/cg_analysis.log
touch cg_analysis.log
touch cg_analysis.out

cframe=0
echo ">> xtclast = $xtclast, cframe = $cframe"

time mummi_cganalysis \
                  --simname $jobid \
                  --path $locpath ${nogpu} \
                  --pathremote $outpath \
                  --siminputs $outpath \
                  --fstype mummi \
                  --fbio mummi \
                  --simbin gmx \
                  --backend GROMACS_PARTS \
                  --simcores $OMP_NUM_THREADS \
                  --nprocs 1 \
                  --stopsimtime 100 \
                  --simruntime 0.5 \
                  --logstdout \
                  --loglevel 2 \
                  --mini \
                  --fcount $cframe 2>&1 | tee $outfile
retval=$?
if [[ "$retval" == "0" ]]; then
  echo "Simulation was successful"
  cd /tmp/workdir
  ls .
  xtcfile=$(find . -name traj_comp.xtc) || true
  xtcdir=$(dirname $xtcfile) || true
  cd $xtcdir
  python3 /get_sim_length.py -x $xtcfile || true
  cd /tmp/workdir
fi
