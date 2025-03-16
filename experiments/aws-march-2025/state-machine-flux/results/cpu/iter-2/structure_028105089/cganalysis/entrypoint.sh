
  
  jobid="structure_028105089"
  outpath="/mnt/efs/iter-1/structure_028105089/cganalysis"
  

  echo ">> jobid        = $jobid"
  echo ">> outpath      = $outpath"
  
  echo ">> hostname     = "$(hostname)
  mkdir -p -v $outpath; cd $outpath

  

  MUMMI_APP=/opt/clones/mummi-ras
  MUMMI_RESOURCES=/opt/clones/mummi_resources
  export MUMMI_APP MUMMI_RESOURCES
  export MUMMI_ROOT=$(dirname $(dirname $outpath))
  locpath=$(dirname $outpath)
  export OMPI_COMM_WORLD_RANK=1
  export OMP_NUM_THREADS=$(nproc)
  mkdir -p $locpath/tmp
  cd ${locpath}
  ls
  cframe=0
  echo ">> xtclast = $xtclast, cframe = $cframe"
  mummi_cganalysis \
        --simname ${jobid} \
        --path $locpath/createsim \
        --pathremote $outpath \
        --siminputs $outpath \
        --fstype mummi \
        --fbio mummi \
        --simbin gmx \
        --backend GROMACS_PARTS \
        --simcores ${OMP_NUM_THREADS} \
        --nprocs 1 \
        --stopsimtime 100 \
        --simruntime 0.5 \
        --logstdout \
        --loglevel 2 \
        --no-gpu \
        --mini \
        --fcount $cframe
      echo $?


  