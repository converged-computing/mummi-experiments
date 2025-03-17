
  
  jobid="structure_007964002"
  outpath="/mnt/efs/iter-2/structure_007964002/mlrunner"
  

  echo ">> jobid        = $jobid"
  echo ">> outpath      = $outpath"
  
  echo ">> hostname     = "$(hostname)
  mkdir -p -v $outpath; cd $outpath

  

  mummi_mlserver_nnodes=1
  MUMMI_APP=/opt/clones/mummi-ras
  export MUMMI_RESOURCES=/opt/clones/mummi_resources
  export MUMMI_APP
  export MUMMI_ROOT=$(dirname $(dirname $outpath))
  ws=$MUMMI_ROOT
  model="/opt/clones/mummi_resources/ml/chonky-model/CG_pos_data_summary_pos_dis_C1_v1.npz"
  resources="martini3-validator"
  complex="ras-rbdcrd-ref-CG.gro"
  cd $outpath
  cmd="mummi-ml start --jobid ${jobid} --workspace=${ws} --outdir=${outpath} --tag mlrunner --encoder-model ${model} --ml-outdir=${ws} --device gpu --feedback --resources ${resources} --complex=${complex}"
  NUM_THREADS=$(nproc)
  export OMP_NUM_THREADS=$NUM_THREADS
  export KERAS_BACKEND='theano'
  umask 007
  python $MUMMI_APP/mummi_ras/scripts/create_organization.py
  echo "$cmd"
  $cmd
  retval=$?
  # Move into respective output directory so easy to find
  if [[ "${retval}" != "0" ]]; then
      exit $retval
  fi
  # This assumes we will just generate one output file
  outfile=$(ls $outpath/$jobid_*.gro)
  mv $outfile $outpath/$jobid.gro
  exit $retval


  