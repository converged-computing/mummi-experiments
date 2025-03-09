# CPU Node Selector

This portion of the experiment uses the state machine operator to select an ideal node type for the createsims step. To be consistent in our step, we use the same createsims container that is pre-baked with the analysis and script to process the same gromacs input. We will have the output times for each run, and can choose the instance type based on that.

## Docker

In order to make a fair comparison, we need to run the analysis on the same input data. That is done by way of building the container first.

```bash
docker build -t ghcr.io/converged-computing/mummi-experiments:cpu-node-selector .

# Run, but be careful if your machine will cough up a fan.
docker run ghcr.io/converged-computing/mummi-experiments:cpu-node-selector
docker push ghcr.io/converged-computing/mummi-experiments:cpu-node-selector
```

I'm working on the ability to select a node next, and I'll also need to figure out how to make a cluster with different node types. If we require, for example, all of the same node type to start, it's not clear if we should do a design that is horizontal (running the same type in the same state machines over time) or vertical (running as the same step in multiple state machines so the cluster does not need to scale). 

## Instance Types

Okay, let's replace the p4d.24xlarge with another suitable instance type. Given that the p4d.24xlarge was included for its high CPU and networking capabilities, we'll aim for a similar profile but without the GPU focus.


## Notes

- Figuring out which resource type is best would be a second idea/goal.
- Idea would be to run each step on different nodes, and choose minimum time.
- But for this study we assume each stage has an assigned node type.
- Compare potpourri cluster with homogeneous cluster (time and cost)
- At the beginning, create N of node type. As the composition of the cluster changes, the autoscaler needs to kick in to provision the node needed.

If time, think of ways to have state machine operator act as node selector (this study)

