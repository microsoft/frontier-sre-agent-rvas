# Grubify - Food Delivery App

A food delivery application built with a React TypeScript frontend and a .NET backend. Its source
is retained for Azure SRE Agent investigation and remediation exercises.

## 🍕 Features

- **Modern UI**: Beautiful, responsive design inspired by popular food delivery apps
- **Real Food Content**: Sample restaurants and food items with real images from Unsplash
- **Complete Food Delivery Flow**: Browse restaurants → Add to cart → Checkout → Track orders
- **Azure Container Apps**: Scalable, serverless container hosting

## 🏗️ Architecture

- **Frontend**: React 18 + TypeScript + Material-UI
- **Backend**: .NET 9 Web API with RESTful endpoints
- **Infrastructure**: Azure Container Apps, with images published to GitHub Packages
- **Workshop deployment**: Terraform consumes the existing public GitHub Packages images

## Where the remediation exercise ends

This application is the subject of the Azure SRE Agent remediation exercise. The exercise ends at
the pull request:

1. The agent diagnoses the production incident, opens an issue, and opens a pull request carrying
   the source fix. It never pushes to the default branch and never merges its own pull request.
2. You review the two artifacts it produced. That is the deliverable, and the exercise ends here.

Approving, merging and re-releasing are deliberately outside the exercise. What is being assessed
is the quality of the investigation and of the proposed change.

## How the workshop runs the application

The workshop does not build or publish Grubify. Terraform deploys the two existing public images:

- `ghcr.io/microsoft/frontier-sre-agent-rvas/grubify-api:latest`
- `ghcr.io/microsoft/frontier-sre-agent-rvas/grubify-frontend:latest`

Source remediation ends at the pull request. Publishing a modified image is intentionally outside
the workshop scope.

[`scripts/verify-cart-resilience.sh`](scripts/verify-cart-resilience.sh) replays 200 cart writes
against a deployed interface and fails unless the error rate stays within the threshold. Use it to
measure the behavior of a deployed interface.

