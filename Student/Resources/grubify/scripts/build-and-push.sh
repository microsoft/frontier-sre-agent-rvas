#!/bin/bash
# =============================================================================
# Build & Push Grubify container images to Azure Container Registry (ACR)
#
# Builds both services and pushes them to the target ACR using ACR Tasks
# (`az acr build`), which builds remotely in Azure:
#   - GrubifyApi        -> grubify-api:latest
#   - grubify-frontend  -> grubify-frontend:latest
#
# Why `az acr build` (server-side) instead of a local `docker build`:
#   * Produces linux/amd64 images regardless of the host CPU (e.g. arm64),
#     matching the architecture Azure Container Apps runs on.
#   * No local Docker daemon required; authentication is handled by Azure CLI.
#   * The build context is uploaded to ACR and built + pushed in one step.
#
# Target registry (resource ID):
#   /subscriptions/<Your Subscription ID>/resourceGroups/
#   rg-frc-spoke-foodapp-paas/providers/Microsoft.ContainerRegistry/registries/
#   acrvflta4iebz8food
#
# Prerequisites:
#   * Azure CLI (`az`) installed and logged in (`az login`)
#   * AcrPush (or Contributor) role on the target ACR
#
# Usage:
#   ./scripts/build-and-push.sh [TAG]                         # TAG defaults to "latest"
#   ./scripts/build-and-push.sh v1.0.0                        # build & push :v1.0.0 (+ :latest)
#   IMAGE_TAG=v1.0.0 ./scripts/build-and-push.sh              # set the tag via env var
#   ALSO_TAG_LATEST=false ./scripts/build-and-push.sh v1.0.0  # do NOT also update :latest
#   API_VERSION=v2 ./scripts/build-and-push.sh v1.0.0         # set the API build arg
#
# Tag precedence: CLI argument > IMAGE_TAG env var > "latest".
# When a versioned tag is pushed, ":latest" is also updated by default so it
# keeps pointing to the newest release (disable with ALSO_TAG_LATEST=false).
# =============================================================================
set -euo pipefail

# --- Target configuration (the specific ACR these images must land in) -------
SUBSCRIPTION_ID="<Your Subscription ID>"
RESOURCE_GROUP="rg-frc-spoke-foodapp-paas"
ACR_NAME="acrvflta4iebz8food"


# --- Image configuration -----------------------------------------------------
# Tag precedence: CLI argument ($1) > IMAGE_TAG env var > "latest".
IMAGE_TAG="${1:-${IMAGE_TAG:-latest}}"
API_IMAGE="grubify-api"
FRONTEND_IMAGE="grubify-frontend"
API_VERSION="${API_VERSION:-v1}"   # consumed by GrubifyApi/Dockerfile ARG

# When pushing a versioned tag, also update ":latest" so it points to this
# release. No-op when IMAGE_TAG is already "latest". Disable: ALSO_TAG_LATEST=false
ALSO_TAG_LATEST="${ALSO_TAG_LATEST:-true}"
if [ "$ALSO_TAG_LATEST" = "true" ] && [ "$IMAGE_TAG" != "latest" ]; then
  TAG_LATEST_TOO=1
else
  TAG_LATEST_TOO=0
fi

# --- Resolve paths relative to the repository root ---------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
API_CONTEXT="$REPO_ROOT/GrubifyApi"
FRONTEND_CONTEXT="$REPO_ROOT/grubify-frontend"

echo "🍕 Grubify — build & push container images"
echo "=============================================="
echo "  Registry : $ACR_NAME (rg: $RESOURCE_GROUP)"
echo "  API      : $API_IMAGE:$IMAGE_TAG   (API_VERSION=$API_VERSION)"
echo "  Frontend : $FRONTEND_IMAGE:$IMAGE_TAG"
if [ "$TAG_LATEST_TOO" -eq 1 ]; then
  echo "  Also tag : latest (updated to point to $IMAGE_TAG)"
fi
echo "  Platform : linux/amd64"
echo "=============================================="

# --- 1. Verify Azure CLI is available ----------------------------------------
if ! command -v az >/dev/null 2>&1; then
  echo "❌ Azure CLI (az) not found. Install: https://aka.ms/azure-cli" >&2
  exit 1
fi

# --- 2. Verify Azure authentication ------------------------------------------
if ! az account show >/dev/null 2>&1; then
  echo "❌ Not logged in to Azure. Run: az login" >&2
  exit 1
fi

# --- 3. Select the target subscription ---------------------------------------
echo "🔐 Setting subscription: $SUBSCRIPTION_ID"
az account set --subscription "$SUBSCRIPTION_ID"

# --- 4. Verify access to the target registry ---------------------------------
echo "🔎 Verifying access to ACR '$ACR_NAME'..."
if ! az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" \
      --query name --output tsv >/dev/null 2>&1; then
  echo "❌ Cannot access ACR '$ACR_NAME' in resource group '$RESOURCE_GROUP'." >&2
  echo "   Verify the name and that you hold AcrPush/Contributor on it." >&2
  exit 1
fi

# Assemble --image flags (one per tag); a single `az acr build` applies all
# tags to the same built image, so :latest is bit-for-bit identical to :TAG.
API_IMAGE_ARGS=(--image "${API_IMAGE}:${IMAGE_TAG}")
FRONTEND_IMAGE_ARGS=(--image "${FRONTEND_IMAGE}:${IMAGE_TAG}")
if [ "$TAG_LATEST_TOO" -eq 1 ]; then
  API_IMAGE_ARGS+=(--image "${API_IMAGE}:latest")
  FRONTEND_IMAGE_ARGS+=(--image "${FRONTEND_IMAGE}:latest")
fi

# --- 5. Build & push the backend (GrubifyApi) --------------------------------
echo ""
echo "🏗️  Building & pushing $API_IMAGE:$IMAGE_TAG ..."
az acr build \
  --registry "$ACR_NAME" \
  "${API_IMAGE_ARGS[@]}" \
  --platform linux/amd64 \
  --build-arg "API_VERSION=${API_VERSION}" \
  "$API_CONTEXT"

# --- 6. Build & push the frontend (grubify-frontend) -------------------------
echo ""
echo "🏗️  Building & pushing $FRONTEND_IMAGE:$IMAGE_TAG ..."
az acr build \
  --registry "$ACR_NAME" \
  "${FRONTEND_IMAGE_ARGS[@]}" \
  --platform linux/amd64 \
  "$FRONTEND_CONTEXT"

# --- 7. Confirm the pushed tags ----------------------------------------------
echo ""
echo "✅ Push complete. Current tags in $ACR_NAME:"
for repo in "$API_IMAGE" "$FRONTEND_IMAGE"; do
  tags="$(az acr repository show-tags --name "$ACR_NAME" --repository "$repo" \
            --output tsv 2>/dev/null | tr '\n' ' ' || true)"
  echo "  - $repo: ${tags:-<none>}"
done

echo "=============================================="
echo "🎉 Done — pushed:"
echo "   ${ACR_NAME}.azurecr.io/${API_IMAGE}:${IMAGE_TAG}"
echo "   ${ACR_NAME}.azurecr.io/${FRONTEND_IMAGE}:${IMAGE_TAG}"
if [ "$TAG_LATEST_TOO" -eq 1 ]; then
  echo "   ${ACR_NAME}.azurecr.io/${API_IMAGE}:latest"
  echo "   ${ACR_NAME}.azurecr.io/${FRONTEND_IMAGE}:latest"
fi
