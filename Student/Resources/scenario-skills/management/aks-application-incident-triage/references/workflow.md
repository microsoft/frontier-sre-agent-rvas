# Evidence collection and analysis

## Collection

### 1. Read pod and event snapshots without changing the cluster

Capture each output separately in the approved private evidence store and repeat the pod read at the approved end of the window. Match UIDs and container names across snapshots. Retain continuation or incomplete list evidence. Do not use --all-namespaces, create a debug pod or read Secrets by default. An unverified context blocks collection.

```powershell
kubectl --context $CONTEXT --namespace $NS get pods -o json
kubectl --context $CONTEXT --namespace $NS get events -o json
```

### 2. Read one affected pod and optionally approved previous logs

The logs command is optional and requires explicit log content permission. Skip it when previous logs are unavailable and retain that reason; do not swallow an access error. Logs, pod environment values and event messages can contain confidential data. Do not copy raw content into customer reports.

```powershell
kubectl --context $CONTEXT --namespace $NS get pod $POD -o json
kubectl --context $CONTEXT --namespace $NS logs $POD --container $CONTAINER --previous --tail=200 --timestamps=true
```

### 3. Classify normalized pod symptoms locally

Follow [the normalization rules](../../../shared/references/operational-evidence.md) and [synthetic example](./evidence-example.json). Restart delta is observed change within the window, not lifetime restartCount. Missing first snapshots, replaced UIDs or unknown termination times must not be silently converted to zero.

```powershell
python tools/operational_analysis.py --scenario aks-application-incident-triage --input $INPUT --contract references/output-contract.json --output aks-private-result.json --sharing-output aks-sharing-draft.json
```

## Analysis rules

1. Separate Pending, Failed, Unknown, readiness, waiting reasons, recent OOM kills and restart delta above the customer threshold. Do not flag a successfully completed job merely because it is not ready.
2. Match immutable UIDs and container identities; a newly created replacement pod cannot be compared by name with a prior pod. Include init container failures and identify missing status or history.
3. Use CrashLoopBackOff, ImagePullBackOff, probe events and OOM evidence as symptoms that narrow hypotheses. Do not infer incorrect memory limits or image permissions without supporting configuration and logs.
4. A lastState terminated OOMKilled without a timestamp in the window is historical evidence, not a confirmed new incident. A ready pod is not proof that the whole application is available.
5. Propose the next targeted check and mitigation draft. Restarts, deletions, scaling, resource changes, debug containers, exec and network tests that create workload activity require separate approval.

## Known limits

- Kubernetes event retention and pod replacement can remove the necessary history. Empty pod lists or denied namespace reads are Not assessed.
- The local classifier assesses normalized pod observations, not dependencies, full request paths, network policy reachability or a proven root cause.

## Expected validation cases

- Healthy: running ready pods without waiting reason, recent OOM or threshold breach produce no configured symptom.
- Finding: CrashLoopBackOff, a recent OOM event or restart delta above threshold produces Needs attention with symptom counts, not claimed root cause.
- Missing: empty list, denied read, unknown readiness or absent observation delta is Not assessed. Duplicate UIDs and negative deltas are rejected.

## Sources

- [AKS pod crash loops and targeted read diagnostics](https://learn.microsoft.com/troubleshoot/azure/azure-kubernetes/create-upgrade-delete/pod-stuck-crashloopbackoff-mode) (consulted 2026-10-21).
- [Validate health across the complete critical flow](https://learn.microsoft.com/azure/well-architected/reliability/reliability-test) (consulted 2026-10-21).
