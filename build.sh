#!/usr/bin/env bash
#
# Build and push the papishares image. It does NOT deploy - ArgoCD does that,
# from k8s-charts/argocd/applications/papishares.yaml.
#
# To ship a new build:
#   ./build.sh                       # builds and pushes, prints the tag
#   <edit chart/values.yaml image.tag to the printed tag, commit, push>
#
# That second step is the deployment. Keeping it a separate, reviewable commit
# is the whole point of dropping the "latest" tag: the git history now says
# what is running and when it changed, and reverting the commit rolls back.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

REPO="ophintor/papishares"

# Same scheme as ophintor/jenkins-agent: YYYY.MM.DD-N, with N counting builds
# within the day so two builds on one day never collide.
DATE="$(date +%Y.%m.%d)"
N=1
while docker manifest inspect "${REPO}:${DATE}-${N}" >/dev/null 2>&1; do
  N=$((N + 1))
done
TAG="${DATE}-${N}"

# --platform because the cluster is amd64 and this is usually built on a Mac.
docker build --platform linux/amd64 -t "${REPO}:${TAG}" . --push

echo
echo "Pushed ${REPO}:${TAG}"
echo "Now set image.tag to \"${TAG}\" in chart/values.yaml, commit and push."
