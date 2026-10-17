.DEFAULT_GOAL := build

.PHONY: build image build-web clean-web apm

build:
	@set -e; \
	find "$(PARKING_MANAGER_ROOT)" -type f -name package.json -printf '%h\n' | sort -u | while IFS= read -r app; do \
		echo "==> Building $$app"; \
		( cd "$$app" && npm install && npm run build --if-present ); \
	done

image:
	@set -e; \
	find "$(PARKING_MANAGER_ROOT)" -type f -name Dockerfile -printf '%h\n' | sort -u | while IFS= read -r app; do \
		echo "==> Building image for $$app"; \
		image_name=$$(echo "$$app" | tr '/.' '-' | sed 's/-$$//'); \
		( cd "$$app" && docker build -t "$$image_name:local" . ); \
	done

build-web: clean-web
	@echo "Building _site..."
	@rm -rf _site
	@mkdir -p _site
	@# Web source (index.html + assets)
	@cp -r web/. _site/
	@# Publish the briefing at /signalops/ and preserve the mission board.
	@cp _site/signalops/index.html _site/signalops/missions.html
	@cp _site/signalops/capabilities.html _site/signalops/index.html
	@# README linked from the page
	@cp README.md _site/README.md
	@# Student challenge markdown files (directly in Student/)
	@mkdir -p _site/Student
	@find Student -maxdepth 1 -name "Challenge-*.md" -exec cp {} _site/Student/ \; 2>/dev/null || true
	@# Coach solution markdown files (Coach/ root and Coach/Solutions/)
	@mkdir -p _site/Coach/Solutions
	@find Coach -maxdepth 1 -name "Solution-*.md" -exec cp {} _site/Coach/ \; 2>/dev/null || true
	@find Coach/Solutions -maxdepth 1 -name "Solution-*.md" -exec cp {} _site/Coach/Solutions/ \; 2>/dev/null || true
	@# Standalone SRE SignalOps challenge track
	@mkdir -p _site/sre-signalops/Coach/Deployment _site/sre-signalops/Coach/Missions
	@cp "SRE SignalOps/README.md" _site/sre-signalops/README.md
	@cp "SRE SignalOps/Lab-Details.md" _site/sre-signalops/Lab-Details.md
	@# Publish only deployment documentation and source; never local state or inputs.
	@mkdir -p _site/sre-signalops/Deployment/Bicep _site/sre-signalops/Deployment/Terraform/infra/modules/workload/templates
	@cp "SRE SignalOps/Deployment/README.md" _site/sre-signalops/Deployment/
	@cp "SRE SignalOps/Deployment/Bicep/"*.md _site/sre-signalops/Deployment/Bicep/
	@cp "SRE SignalOps/Deployment/Terraform/"*.md _site/sre-signalops/Deployment/Terraform/
	@node scripts/package-signalops-terraform.cjs
	@tar -czf _site/sre-signalops/Deployment/Terraform/signalops-terraform.tar.gz -C _site/sre-signalops/Deployment/Terraform infra
	@cp -r "SRE SignalOps/Missions" _site/sre-signalops/Missions
	@cp "SRE SignalOps/azure.yaml" _site/sre-signalops/azure.yaml
	@cp -r "SRE SignalOps/Config" _site/sre-signalops/Config
	@mkdir -p _site/sre-signalops/infra/modules
	@cp "SRE SignalOps/infra/"*.bicep _site/sre-signalops/infra/
	@cp "SRE SignalOps/infra/modules/"*.bicep _site/sre-signalops/infra/modules/
	@mkdir -p _site/sre-signalops/Scripts
	@cp "SRE SignalOps/Scripts/README.md" _site/sre-signalops/Scripts/README.md
	@find "SRE SignalOps/Scripts" -maxdepth 1 -name "*.ps1" -exec cp {} _site/sre-signalops/Scripts/ \; 2>/dev/null || true
	@cp "SRE SignalOps/Coach/README.md" _site/sre-signalops/Coach/README.md
	@cp "SRE SignalOps/Coach/Lab-Details.md" _site/sre-signalops/Coach/Lab-Details.md
	@cp "SRE SignalOps/Coach/Customer-Demo-00-02.md" "SRE SignalOps/Coach/Capability-Briefing-Notes.md" "SRE SignalOps/Coach/Grubify-Lab-Briefing-Notes.md" _site/sre-signalops/Coach/
	@cp "SRE SignalOps/Coach/Deployment/"*.md _site/sre-signalops/Coach/Deployment/
	@cp "SRE SignalOps/Coach/Missions/"*.md _site/sre-signalops/Coach/Missions/
	@echo "Done → _site/"

clean-web:
	@rm -rf _site
	@echo "Cleaned _site/"

apm:
	apm install --target copilot
