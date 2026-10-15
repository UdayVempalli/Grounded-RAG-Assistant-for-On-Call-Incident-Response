# Pod Stuck in Pending

## Symptoms
- Pod stuck in `Pending`; `kubectl get pods` shows it never gets scheduled.
- `kubectl describe pod <name>` shows `0/3 nodes are available` or `Insufficient cpu/memory`.
- The pod has no events after `Scheduled` (it was never assigned to a node).

## Diagnosis
1. Check why it was not scheduled: `kubectl describe pod <name>` — read the `Events` section for the scheduler's reason.
2. Check node capacity: `kubectl top nodes` — if every node is at capacity, the pod waits.
3. Check taints and tolerations: `kubectl describe node <node>` — a taint without a matching toleration blocks scheduling.
4. Check the PVC: `kubectl get pvc` — a Pending PVC (no storage) blocks the pod.

## Mitigation
- Insufficient capacity: scale the node pool or reduce the pod's resource requests.
- Taint mismatch: add the toleration to the pod spec, or remove the taint from the node.
- Pending PVC: check the StorageClass and provisioner; a missing provisioner leaves the PVC Pending.
- Node selector / affinity: if the pod requires a label no node has, fix the label or the selector.

## Escalation
- Page the platform on-call if pods stay Pending for more than 10 minutes or if a whole node pool is unschedulable.
