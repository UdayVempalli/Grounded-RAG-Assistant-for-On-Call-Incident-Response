# Node NotReady

## Symptoms
- `kubectl get nodes` shows a node in `NotReady`.
- Pods on that node stop receiving traffic (they are evicted or unreachable).
- `kubectl describe node <node>` shows `KubeletNotReady` or `PLEG is not healthy`.

## Diagnosis
1. Check the node status: `kubectl describe node <node>` — read the `Conditions` section for the reason.
2. Check the kubelet: `systemctl status kubelet` on the node — a stopped kubelet makes the node NotReady.
3. Check disk pressure: `df -h` on the node — a full disk stops the kubelet (see DiskPressure).
4. Check the container runtime: `systemctl status containerd` — a dead runtime means no pods can run.

## Mitigation
- Restart the kubelet: `systemctl restart kubelet` (the node rejoins once the kubelet is healthy).
- Free disk: clear logs or images if the disk is full (see DiskPressure).
- Restart the runtime: `systemctl restart containerd` if the runtime is dead.
- Cordon and drain if the node will not recover: `kubectl cordon <node>` then `kubectl drain <node> --ignore-daemonsets`.

## Escalation
- Page the platform on-call if a node stays NotReady for more than 10 minutes or if multiple nodes go NotReady.
