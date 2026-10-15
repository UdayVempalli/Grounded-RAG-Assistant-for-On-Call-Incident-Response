# ImagePullBackOff

## Symptoms
- Pod stuck in `ImagePullBackOff` or `ErrImagePull`; `kubectl get pods` shows the pod never reaches Running.
- `kubectl describe pod <name>` shows `Failed to pull image` or `ImagePullBackOff` events.
- The pod has zero restarts (it never started), unlike CrashLoopBackOff.

## Diagnosis
1. Check the image name and tag: `kubectl describe pod <name>` — look for a typo in the image name or a tag that does not exist.
2. Check the registry: `docker pull <image>` from a machine with access — if it fails there, the image or tag is wrong.
3. Check the image pull secret: `kubectl get secret <name>` — a missing or expired secret gives `401 Unauthorized` in the events.
4. Check the registry: if the registry is down or the network blocks it, every pod on the node fails to pull.

## Mitigation
- Typo or bad tag: fix the image name or tag in the deployment and re-apply.
- Missing secret: create it: `kubectl create secret docker-registry <name> --docker-server=<registry> --docker-username=<user> --docker-password=<pass>`.
- Expired secret: rotate it and restart the pod.
- Registry down: wait for the registry; do not keep restarting the pod (backoff already throttles it).

## Escalation
- Page the platform on-call if the registry is down for more than 10 minutes or if every pod on a node fails to pull.
