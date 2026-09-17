SCENARIOS  ?=scripts

.PHONY: validate validate-food validate-parking \
		baseline-traffic food-traffic parking-traffic \
		break-food food-status \
        trigger-nginx-down restore-nginx \
        trigger-nsg-block restore-nsg-block \
        trigger-udr restore-udr \
		trigger-parking-report restore-parking-report \
		trigger-parking-service-down restore-parking-service \
		trigger-parking-down restore-parking \
        trigger-parking-chaos restore-parking-chaos \
		grant-agent-vm-remediation check-cost-access \
        parking-status

# ── Lab scenario targets ────────────────────────────────────────────────────

## validate: check lab infrastructure health (all challenges)
validate:
	$(SCENARIOS)/validate.sh

## validate-food: check Grubify / Sample Food app health (Challenges 06, 14, 15)
validate-food:
	$(SCENARIOS)/validate-sample-food-app.sh

## validate-parking: check the Parking Manager Web App, VNet integration, and APIs
validate-parking:
	@bash $(SCENARIOS)/validate-parking-manager.sh

## baseline-traffic: generate IaaS/network traffic (Challenges 00, 12, 13, 17)
baseline-traffic:
	@$(SCENARIOS)/generate-baseline-traffic.sh

## food-traffic: generate Grubify food app traffic (Challenges 00, 08)
food-traffic:
	@$(SCENARIOS)/generate-sample-food-app-traffic.sh

## parking-traffic: generate traffic through the Parking Manager frontend (Challenge 00)
parking-traffic:
	@bash $(SCENARIOS)/generate-parking-manager-traffic.sh

## break-food: inject HTTP 5xx fault into Grubify (Challenges 06, 14, 15)
break-food:
	$(SCENARIOS)/break-sample-food-app.sh

## food-status: check Grubify container image deployment status (Challenges 06, 14)
food-status:
	$(SCENARIOS)/show-sample-food-status.sh

## trigger-nginx-down: stop nginx on web-tier VMs to simulate outage (Challenge 11)
trigger-nginx-down:
	$(SCENARIOS)/trigger-nginx-down.sh

## restore-nginx: restart nginx on web-tier VMs (Challenge 11)
restore-nginx:
	$(SCENARIOS)/restore-nginx.sh

## trigger-nsg-block: inject NSG deny rule to block app→DB traffic (Challenge 12)
trigger-nsg-block:
	$(SCENARIOS)/trigger-nsg-block.sh

## restore-nsg-block: remove injected NSG deny rule (Challenge 12)
restore-nsg-block:
	$(SCENARIOS)/restore-nsg-block.sh

## trigger-udr: inject asymmetric UDR to break routing (Challenge 13)
trigger-udr:
	$(SCENARIOS)/trigger-udr-asymmetry.sh

## restore-udr: remove injected UDR asymmetry (Challenge 13)
restore-udr:
	$(SCENARIOS)/restore-udr-asymmetry.sh

## trigger-parking-report: emit synthetic Parking VM health events (Challenge 10)
trigger-parking-report:
	$(SCENARIOS)/trigger-parking-api-down.sh

## restore-parking-report: restore synthetic Parking VM health state (Challenge 10)
restore-parking-report:
	$(SCENARIOS)/restore-parking-api.sh

## trigger-parking-service-down: stop the Paris Parking API service (Challenge 15)
trigger-parking-service-down:
	$(SCENARIOS)/trigger-parking-service-down.sh

## restore-parking-service: start and validate the Paris Parking API service (Challenge 15)
restore-parking-service:
	$(SCENARIOS)/restore-parking-service.sh

## trigger-parking-down: compatibility alias for the Challenge 10 reporting signal
trigger-parking-down: trigger-parking-report

## restore-parking: compatibility alias for the Challenge 10 reporting signal
restore-parking: restore-parking-report

## grant-agent-vm-remediation: grant the agent least-privilege VM restart and Run Command access
grant-agent-vm-remediation:
	$(SCENARIOS)/grant-agent-vm-remediation.sh

## check-cost-access: verify Cost Management read access with bounded throttling retries
check-cost-access:
	$(SCENARIOS)/check-cost-management-access.sh

## trigger-parking-chaos: inject Lisbon API latency chaos
trigger-parking-chaos:
	$(SCENARIOS)/trigger-parking-chaos.sh

## restore-parking-chaos: disable Parking Manager chaos injection
restore-parking-chaos:
	$(SCENARIOS)/restore-parking-chaos.sh

## parking-status: show current Parking Manager VM health control state
parking-status:
	@health_control_url="$$(terraform -chdir="$(INFRA_DIR)" output -json | jq -er '."parking_vm_health_control_url".value // empty')"; \
	if [ -z "$${health_control_url}" ]; then \
		echo "Could not determine parking_vm_health_control_url from $(INFRA_DIR)." >&2; \
		exit 1; \
	fi; \
	curl -sfS "$${health_control_url}/api/vm-health/state"; \
	echo
