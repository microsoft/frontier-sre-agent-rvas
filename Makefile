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
	@# README linked from the page
	@cp README.md _site/README.md
	@# Student challenge markdown files, preserving nested track directories
	@mkdir -p _site/Student
	@find Student -type f -name "Challenge-*.md" | while IFS= read -r file; do \
		dest="_site/$$(dirname "$$file")"; \
		mkdir -p "$$dest"; \
		cp "$$file" "$$dest/"; \
	done
	@# Resources linked by the SQL Server DBA track
	@mkdir -p _site/Student/Resources
	@cp -r Student/Resources/sql-server-mcp _site/Student/Resources/
	@# Coach indexes and solutions, preserving nested track directories
	@mkdir -p _site/Coach
	@find Coach -type f \( -name "Solution-*.md" -o -name "README.md" \) | while IFS= read -r file; do \
		dest="_site/$$(dirname "$$file")"; \
		mkdir -p "$$dest"; \
		cp "$$file" "$$dest/"; \
	done
	@echo "Done → _site/"

clean-web:
	@rm -rf _site
	@echo "Cleaned _site/"

apm:
	apm install --target copilot
