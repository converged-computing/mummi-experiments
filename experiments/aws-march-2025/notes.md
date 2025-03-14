# Notes

## Overview

I think we should first do experiments that show incremental improvement on different facets of Mummi, with respect to design, and then CPU and GPU (described below). I then think we should choose the best setup and do one more "production" cloud run, maybe with better GPU and larger, and then we can do further looking at the results (or similar).

- Mummi Operator on AWS (represents the old design where the ML server requires an entire node)
   - For each of CPU and GPU (this will assess the tradeoff between the two, assuming limit of cganalysis time)
- State Machine Operator on AWS
   - For each of CPU and GPU (this will assess the tradeoff between the two, assuming limit of cganalysis time)
   - For each of CPU and GPU starting at max size and allowing cluster to downscale
- State Machine Operator with Singularity and Flux (Bare Metal AWS)
   - For each of CPU and GPU (if possible)

That will be 8 experiments total. Autoscaling is not done for the Mummi Operator because it would not make a difference - the stopping point is manual and the cluster will remain filled until the end. For Kubernetes setups, I can collect metadata about image pulls and events. For the state machine operator runs I can collect additional timings of the orchestration. These are the comparisons we can make:

- CPU vs. GPU for each setup and between setups
- Bare Metal vs. Kubernetes, where notably, Kubernetes can have autoscaling
- The improvement to Mummi removing rabbitMQ and the MLServer vs running the ML as a single job
- Container pulling times between the setups

For CPU nodes, we will ask for 94/96 cores per task. For GPU, since the GPU has 1/node, that specification on the request will handle the scheduling topology. You will need the repository root here to create the clusters, etc.

```bash
git clone https://github.com/converged-computing/mummi-experiments
cd ./mummi-experiments/experiments/aws-march-2025
```

Note that the State Machine Operator setup requires the mlrunner container, which is deployed from the [mummi-operator](https://github.com/converged-computing/mummi-operator). 


## Metrics to Collect

 - Timing for events (Kubernetes and via the manager)
 - Total time for experiment (able to calculate cost for entire cluster)
 - Number of outputs for each step produced (e.g., the ML server produces too many)
 - Excess of outputs (iterations from ML server AND additional jobs that can't be used)
 - A cool angle would be to use the cost analyzer to run a mock workflow with different designs

## Discussion and Questions

 - The scale for the experiments (see suggestion above)
    - 6 state machines (18 jobs total) for Mummi Operator comparison
    - 10 jobs total for setups that afford downsizing.
    - Need a way to monitor when nodes come up and down (Kubernetes event exporter?)
    - For node types, GPU and CPU
 - Run experiments on different clusters
 - We are stopping cganalysis at 30 minutes
 - Save all output data (includes timings)
 - Other features I am forgetting? Vertical pod autoscaling?
 - For AWS, I'm having trouble with getting the shared storage working (at least haven't yet). 
 
High level, because we are demonstrating the features moreso than mummi, I think cutting at 30 minutes (or even sooner) is reasonable. I also don't think the output of Mummi is as important as the overall timings, unless there is something interesting with respect to performance on CPU vs. GPU. We will save everything regardless.

## TODO Vanessa

- Come up with random patterns to run simulations of workflows with the state machine operator.

