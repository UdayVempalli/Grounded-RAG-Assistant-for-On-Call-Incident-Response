# DNS Resolution Failure

## Symptoms
- Pods fail to reach services by name (`getaddrinfo ENOTFOUND`, `Name or service not known`).
- `curl` by IP works, but `curl` by hostname fails.
- Only some pods are affected (the ones on a specific node or after a CoreDNS restart).

## Diagnosis
1. Test DNS from the pod: `kubectl exec <pod> -- nslookup kubernetes.default` — if this fails, DNS is broken in the pod.
2. Check the pod's DNS config: `kubectl exec <pod> -- cat /etc/resolv.conf` — the nameserver should point to the cluster DNS service.
3. Check CoreDNS: `kubectl get pods -n kube-system -l k8s-app=kube-dns` — if CoreDNS pods are down, nothing resolves.
4. Check CoreDNS logs: `kubectl logs -n kube-system -l k8s-app=kube-dns` — look for `SERVFAIL`, `timeout`, or `refused`.

## Mitigation
- Restart CoreDNS: `kubectl rollout restart deploy/coredns -n kube-system` (CoreDNS is stateless; a restart is safe).
- Fix the resolv.conf: if the pod has a custom `dnsConfig`, remove it (the default points to cluster DNS).
- Check the Service: `kubectl get svc <name>` — a Service with no endpoints gives NXDOMAIN.
- Increase CoreDNS replicas: if DNS is slow under load, scale CoreDNS (it is CPU-bound under query bursts).

## Escalation
- Page the platform on-call if DNS is down cluster-wide for more than 2 minutes.
