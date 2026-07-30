SCENARIOS  ?= Resources/scenarios/scripts

.PHONY: validate validate-food \
        baseline-traffic food-traffic \
        break-food food-status \
        trigger-nginx-down restore-nginx \
        trigger-nsg-block restore-nsg-block \
        trigger-udr restore-udr \
        trigger-parking-down restore-parking \
        trigger-parking-chaos restore-parking-chaos \
        parking-status

# ── Lab scenario targets ────────────────────────────────────────────────────

## validate: check lab infrastructure health (all challenges)
validate:
	$(SCENARIOS)/validate.sh

## validate-food: check Grubify / Sample Food app health (Challenges 06, 14, 15)
validate-food:
	$(SCENARIOS)/validate-sample-food-app.sh

## baseline-traffic: generate IaaS/network traffic (Challenges 00, 12, 13, 17)
baseline-traffic:
	@$(SCENARIOS)/generate-baseline-traffic.sh

## food-traffic: generate Grubify food app traffic (Challenges 00, 08)
food-traffic:
	@$(SCENARIOS)/generate-sample-food-app-traffic.sh

## break-food: inject HTTP 5xx fault into Grubify (Challenges 06, 14, 15)
break-food:
	$(SCENARIOS)/break-sample-food-app.sh

## food-status: check Grubify container image deployment status (Challenges 06, 14)
food-status:
	$(SCENARIOS)/deploy-sample-food-images.sh --status

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

## trigger-parking-down: mark Parking Manager VM APIs unhealthy (Challenges 10, 15)
trigger-parking-down:
	$(SCENARIOS)/trigger-parking-api-down.sh

## restore-parking: restore Parking Manager VM API health (Challenges 10, 15)
restore-parking:
	$(SCENARIOS)/restore-parking-api.sh

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
