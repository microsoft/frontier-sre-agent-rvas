PARKING_MANAGER_ROOT := Student/Resources/parking-manager

.DEFAULT_GOAL := build

.PHONY: build image

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

