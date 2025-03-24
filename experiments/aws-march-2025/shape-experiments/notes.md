# Shape Experiments

Here we are interested in understanding the cost/time tradeoff for different experiment shapes with different allowances for scaling. High level - two types of experiments, each with a parameter sweet, but with different parameters. We have two shapes of jobs:

- low high low
- high low high

And we assume each takes the same amount of time (1 minute). For the experiment with autoscaling, we vary the reaction time of the autoscaler, and allow it to scale up to the maximum set of nodes that could be occupied by all the large jobs at once. For the experiment without autoscaling, we vary the static size of the cluster. For all cases, we compare the actual time spent running the workflow (and cost) with the theoretical best cost (time of running the jobs only). See [notes](notes.md) for more details.


- Autoscaling is on
  - 10 completions
  - low high low (1 4 1), each step 1 minute
  - high low high (4 1 4), each step 1 minute
  - start cluster at 0
  - max size is 40
  - for each experiment, varying reaction time of autoscaler:
    - 30 seconds
    - 1 minute
    - 2 minute

- Autoscaling is off
  - 10 completions
  - low high low (1 4 1), each step 1 minute
  - high low high (4 1 4), each step 1 minute
  - start cluster at sizes:
    - 6 (4s don't fit perfectly, we will get clogging)
    - 8 (should be able to fit sets of 4s)

Start with 6 and 8.

Third experiment to set autoscaling at max size?

20
low high low
2 4 2
high low high
4 2 4

## Overview

I think we should first do experiments that show incremental improvement on different facets of Mummi, with respect to design, and then CPU and GPU (described below). I then think we should choose the best setup and do one more "production" cloud run, maybe with better GPU and larger, and then we can do further looking at the results (or similar).

- Mummi Operator on AWS (represents the old design where the ML server requires an entire node)
   - For each of CPU and GPU (this will assess the tradeoff between the two, assuming limit of cganalysis time)
   - For each of CPU and GPU starting at max size and allowing cluster to downscale
- State Machine Operator on AWS
   - For each of CPU and GPU (this will assess the tradeoff between the two, assuming limit of cganalysis time)
   - For each of CPU and GPU starting at max size and allowing cluster to downscale
- State Machine Operator with Singularity and Flux (Bare Metal AWS)
   - For each of CPU and GPU (if possible)

That will be 10 experiments total. For Kubernetes setups, I can collect metadata about image pulls and events. For the state machine operator runs I can collect additional timings of the orchestration. These are the comparisons we can make:

- CPU vs. GPU for each setup and between setups
- Bare Metal vs. Kubernetes, where notably, Kubernetes can have autoscaling (but doesn't need to)
- The improvement to Mummi removing rabbitMQ and the MLServer vs running the ML as a single job
- Container pulling times between the setups

For CPU nodes, we will ask for 94/96 cores per task. For GPU, since the GPU has 1/node, that specification on the request will handle the scheduling topology. You will need the repository root here to create the clusters, etc.

```bash
git clone https://github.com/converged-computing/mummi-experiments
cd ./mummi-experiments/experiments/aws-march-2025
```

Note that the State Machine Operator setup requires the mlrunner container, which is deployed from the [mummi-operator](https://github.com/converged-computing/mummi-operator). 

## Notes

Figuring out which resource type is best would be a second idea/goal.
Idea would be to run each step on different nodes, and choose minimum time.
But for this study we assume each stage has an assigned node type.
Compare potpourri cluster with homogeneous cluster (time and cost)
At the beginning, create N of node type. As the composition of the cluster changes, the autoscaler needs to kick in to provision the node needed.

If time, think of ways to have state machine operator act as node selector.

## Metrics to Collect

 - Timing for events (Kubernetes and via the manager)
 - Total time for experiment (able to calculate cost for entire cluster)
 - Number of outputs for each step produced (e.g., the ML server produces too many)
 - A cool angle would be to use the cost analyzer to run a mock workflow with different designs

## Discussion and Questions

 - The scale for the experiments (see suggestion above)
    - 10 jobs total, 6 starting size and max size allowed to scale to.
    - Need a way to monitor when nodes come up and down (look at Kubernetes event exporter)
    - For node types, GPU and CPU (ask Loic if interesting to test different types of CPU nodes for stages)
 - Run experiments on different clusters
 - Are we stopping cganalysis at 30 minutes (I'm not sure we can afford it if we don't) (Yes)
 - Save all output data (includes timings)
 - Other features I am forgetting? Vertical pod autoscaling?
 - For AWS, I'm having trouble with getting the shared storage working (at least haven't yet). 
 
High level, because we are demonstrating the features moreso than mummi, I think cutting at 30 minutes (or even sooner) is reasonable. I also don't think the output of Mummi is as important as the overall timings, unless there is something interesting with respect to performance on CPU vs. GPU.

## TODO Vanessa

- Come up with random patterns to run.
- Both AMIs need to be rebuilt with my key added to authorized keys, and the data for the model pre-extracted.
  - [ ] GPU needs re-pull and test with flux
  - [ ] Still need to do CPU (tested on older image)
- [ ] Test entire workflow with shared filesystem - deletion is erroneous. Could fall back to flux archive, but not ideal.


