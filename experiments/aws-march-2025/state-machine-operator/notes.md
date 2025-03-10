# Notes

## Test Runs

- commit for GPU b18bd707f5cfefaef50e32b42b8849b0e05bfd2e (fixed bug for failed job)
- commit for CPU 12557775f9ed56407f1b6a9488547281ee9a201c

### Observations

- The first GPU run did not have the container build with times, this was a mistake on my part (gpu-static). I re-ran it again with a fix (gpu-static-0).
- I notice we are not mapping the nproc for the entire job to the cganalysis run. But we are being consistent in doing that so they are comparable. I might do the autoscaling runs with the improvement if it makes it go faster. We couldn't compare them to these runs anyway.

Update on the above - the nproc is not used meaningfully for gromacs - it's the cores per task that is. It goes into OMP_NUM_THREADS that is what is given to gromacs to find either multi-threading or different cores.
