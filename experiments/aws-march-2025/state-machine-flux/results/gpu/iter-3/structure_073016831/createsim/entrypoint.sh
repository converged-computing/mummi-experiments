
  
  jobid="structure_073016831"
  outpath="/mnt/efs/iter-3/structure_073016831/createsim"
  

  echo ">> jobid        = $jobid"
  echo ">> outpath      = $outpath"
  
  echo ">> hostname     = "$(hostname)
  mkdir -p -v $outpath; cd $outpath

  

  MUMMI_APP=/opt/clones/mummi-ras
  MUMMI_RESOURCES=/opt/clones/mummi_resources
  export MUMMI_APP MUMMI_RESOURCES
  export MUMMI_ROOT=$(dirname $(dirname $outpath))
  locpath=$(dirname $outpath)
  echo "Outpath is $outpath, Local path is $locpath" 
  echo "Number of processes is ${OMP_NUM_THREADS}"
  rm -rf $locpath/tmp
  mkdir -p $locpath/tmp
  cd ${locpath}
  export OMP_NUM_THREADS=$(nproc)
  outfile=$(ls $locpath/mlrunner/structure*.gro)
  echo "MLrunner output file is $outfile"
  cp ${outfile} $locpath/tmp/${jobid}.gro
  cd $locpath/tmp
  mummi_createsim \
    --fstype simple \
    --patch ${jobid} \
    --inpath $(pwd) \
    --outpath $locpath/createsim \
    --outlocal $locpath/tmp \
    --logpath $locpath \
    --loglevel 2 \
    --gromacs gmx \
    --mpi "gmx mdrun" \
    --mini \
    --mdrunopt " -nb gpu -ntmpi 1 -ntomp $OMP_NUM_THREADS -pin off"


  