# On Premise Experiments

This document describes the setup used to run the on prem experiments.

## Platform

The platform used was Lassen at LLNL. Each of the 3 runs was setup as follows:
- CGanalysis is running for 30 mins
- 6 nodes total (1 for the workflow, 2 for createsims and 3 for CGanalysis)
- The workflow stops after 10 completed CGanalysis

Lassen has 4 GPUs per node when the cloud instances only have 1 GPU per node.
To make sure we can do realistic comparisons in the paper, we restrict Flux to 
see only one GPUs per node. Lassen only supports LSF, so we bootstrap Flux using
LSF and during the bootstraping procedure, we restrict how many GPU Flux can
see using the jsrun option `-g 1`.

Each task produces a JSON files that contains timestamps.

## Organization

The directory `gpu` contains 3 folders, one for each iteration.
Each iteration contains all the structures (logs only).

**Note**: there are more completed CGAnalysis than 10 because while we stop the 
workflow after 10, if some CGAnalsysis are already running we do not kill them.
Also, some structures are just valid createsims (CGAnalysis never ran in these).

To find the valid CGanalysis, look for the presence of the file `cg_success`.
They are also included in the list here.

```console
[nMaxCGAnalysis=10] We have computed ['structure_iter00_000000000004', 'structure_iter00_000000000001', 'structure_iter00_000000000002', 'structure_iter00_000000000007', 'structure_iter00_000000000003', 'structure_iter00_000000000008', 'structure_iter00_000000000014', 'structure_iter00_000000000010', 'structure_iter00_000000000012', 'structure_iter00_000000000005'] CGAnalysis
We have computed 10 CGAnalysis, we stop the workflow
```
