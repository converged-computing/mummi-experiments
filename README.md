# Mummi Experiments

These Mummi Experiments will use the [Mummi Operator](https://github.com/converged-computing/mummi-operator) and later derivatives to run Mummi.

- [test-january-2025](test-january-2025): testing Mummi on 6 nodes, a base setup for GPU/CPU nodes.
- [test-february-2025](test-february-2025): testing Mummi via the state machine operator

## Experiment

### High Level

- Mummi is a workflow that represents a state machine, and warrants features that traditional HPC does not easily support (e.g., elasticity)
- We will increasingly need to be aware of the cost / utilization of our resources (regardless of cloud or hpc) and so we want to run a workflow like Mummi in an optimized way.
- The simplest unit to compare is the job - has a clear definition on HPC and in Kubernetes.
- We could compare some performance of a component (e.g., gromacs) but arguably that is more benchmarking the node, network, etc. It's an interesting question but a different one.
- The end-to-end total time for N work is likely what we want to compare across cases.

### Questions we are interested in

- Can we define the quantity of manual intervention required?
- How much of an allocation (on HPC) does a run of Mummi burn?
  - CPU/GPU hours
- Something to do with reproducibility / resiliency of workflow
  - Injecting faults into workflow and seeing if it can recover 
    - Delete a node and see what happens, hardware failure
    - Inject some probability of failure into the application 
    - Valid for workflows in general, but not Mummi's case
- How long does it take us to move from one platform to another?
- How do we compare orchestration between HPC and cloud environments? (not performance of apps but of orchestration, time between things? events?)
  - There are well-defined ways (makespan / critical path - amount of time all components of workflow need, under what circumstances run better)
  - "Excess" -- utilization efficiency
- What is the marginal benefit to adding cloud features?
  - We can start with traditional Mummi, add the state machine and refactored ml runner, then elasticity (3 stages).
  - Measure total times for running each component. We can compare the total time of the MLserver running to the time of each job.
  - Measure excess - the number of MLserver simulations generated that aren't used.
  - We should be able to measure the decrease an excess and improvement (or not) to total wall time of each component.
  
- Something with simulation using the state machine operator?
  - implement state machine library and have flux with backend
  - we'd be able to measure behavior on HPC vs. cloud

## License

HPCIC DevTools is distributed under the terms of the MIT license.
All new contributions must be made under this license.

See [LICENSE](https://github.com/converged-computing/cloud-select/blob/main/LICENSE),
[COPYRIGHT](https://github.com/converged-computing/cloud-select/blob/main/COPYRIGHT), and
[NOTICE](https://github.com/converged-computing/cloud-select/blob/main/NOTICE) for details.

SPDX-License-Identifier: (MIT)

LLNL-CODE- 842614
