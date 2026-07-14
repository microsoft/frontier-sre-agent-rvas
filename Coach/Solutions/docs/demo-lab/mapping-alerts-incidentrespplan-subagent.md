# Mapping: Azure Monitor alert to incident response plan to sub-agent

This document maps every Azure Monitor alert defined in the demo-lab desired state (Terraform) to the incident response plan that matches it and the sub-agent that handles it. It is derived deterministically from the alert rules in `04-terraform/` and the three response plans in `06-sre-agent-configuration/automations/incident-filters/`.

The project defines **three** Azure Monitor alerts, and each has a unique mapping:

| Alerts Defined | Incidente Response Plan (matchato) | SubAgent |
|---|---|---|
| `alert-vflta-food-http-5xx` (Sev1, metric alert HTTP 5xx su Container Apps API) | `sample-food-http-errors` (match per severità Sev1 + `titleContains: food`) | `aca-app-incident-handler` |
| `alert-vflta-nginx-down` (Sev2, display name: “NGINX service down on web tier”) | `web-tier-nginx` (match per severità Sev2 + `titleContains: nginx`) | `iaas-vm-incident-handler` |
| `alert-vflta-denied-flow-spike` (Sev2, display name: “Denied VNet flow spike”) | `network-observability-review` (match per severità Sev2 + esclusione `titleNotContains: nginx`) | `network-traffic-analyst` |

Nota di completezza: nel progetto risultano definiti **3 alert Azure Monitor** in totale, e ciascuno ha un mapping univoco al relativo incident response plan e sub-agent.