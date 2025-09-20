SHELL := /bin/bash

PA       ?= maceff_user001
SID      ?= 001
PORT     ?= 2222
KEYS_DIR ?= keys
PROJ     ?= demo

.PHONY: help build up logs down mirror mirror-watch ssh-pa ssh-admin sa-test claude claude-doctor

help:
	@echo "Targets:"
	@echo "  make build        - docker-compose build"
	@echo "  make up           - start services"
	@echo "  make logs         - follow logs"
	@echo "  make down         - stop services"
	@echo "  make mirror       - snapshot volumes -> sandbox-*"
	@echo "  make mirror-watch - continuous mirroring (if enabled)"
	@echo "  make ssh-pa       - SSH into PA"
	@echo "  make ssh-admin    - SSH into admin"
	@echo "  make sa-test      - run a small SA job from the PA"
	@echo "  make claude       - launch Claude in /shared_workspace/<PROJ>"
	@echo "  make claude-doctor- run 'claude doctor' inside the container"

build:
	docker-compose build

up:
	docker-compose up -d

logs:
	docker-compose logs -f --tail=120

down:
	docker-compose down

mirror:
	docker-compose --profile mirror up --no-deps mirror

mirror-watch:
	docker-compose --profile mirror-watch up mirror-watch

ssh-pa:
	@set -e; \
	key="$${PA_KEY:-}"; \
	if [ -z "$$key" ]; then \
	  base="$$(echo '$(PA)' | sed -E 's/[0-9]+$$//')"; \
	  for cand in "$(KEYS_DIR)/$(PA)" "$$HOME/.ssh/id_ed25519_$(PA)" "$$HOME/.ssh/id_ed25519_$${base}"; do \
	    [ -f "$$cand" ] && key="$$cand" && break; \
	  done; \
	fi; \
	if [ -z "$$key" ] || [ ! -f "$$key" ]; then \
	  echo "PA key not found. Set PA_KEY or create one of: $(KEYS_DIR)/$(PA), $$HOME/.ssh/id_ed25519_$(PA), $$HOME/.ssh/id_ed25519_$${base}"; \
	  exit 1; \
	fi; \
	ssh -i "$$key" -p "$(PORT)" "$(PA)@localhost"

ssh-admin:
	@set -e; \
	key="$${ADMIN_KEY:-}"; \
	if [ -z "$$key" ]; then \
	  for cand in "$(KEYS_DIR)/admin" "$$HOME/.ssh/id_ed25519_admin"; do \
	    [ -f "$$cand" ] && key="$$cand" && break; \
	  done; \
	fi; \
	if [ -z "$$key" ] || [ ! -f "$$key" ]; then \
	  echo "ADMIN key not found. Set ADMIN_KEY or create one of: $(KEYS_DIR)/admin, $$HOME/.ssh/id_ed25519_admin"; \
	  exit 1; \
	fi; \
	ssh -i "$$key" -p "$(PORT)" admin@localhost

sa-test:
	@set -e; \
	key="$${PA_KEY:-}"; \
	if [ -z "$$key" ]; then \
	  base="$$(echo '$(PA)' | sed -E 's/[0-9]+$$//')"; \
	  for cand in "$(KEYS_DIR)/$(PA)" "$$HOME/.ssh/id_ed25519_$(PA)" "$$HOME/.ssh/id_ed25519_$${base}"; do \
	    [ -f "$$cand" ] && key="$$cand" && break; \
	  done; \
	fi; \
	if [ -z "$$key" ] || [ ! -f "$$key" ]; then \
	  echo "PA key not found. Set PA_KEY or create one of: $(KEYS_DIR)/$(PA), $$HOME/.ssh/id_ed25519_$(PA), $$HOME/.ssh/id_ed25519_$${base}"; \
	  exit 1; \
	fi; \
	ssh -i "$$key" -p "$(PORT)" "$(PA)@localhost" '\
		set -euo pipefail; \
		P=$(PA); SID=$(SID); SA=sa_$${P}_$${SID}; \
		WD=/home/$${P}/agent/subagents/$${SID}; \
		LOG=$${WD}/public/logs/make-test.log; \
		sudo -n -u "$${SA}" /usr/local/bin/sa-exec "$${WD}" "$${LOG}" -- ":"; \
		sudo -n -u "$${SA}" /usr/local/bin/sa-exec "$${WD}" "$${LOG}" -- "echo from-make; id; whoami; pwd"; \
		sleep 0.2; tail -n 20 "$${LOG}" \
	'

claude:
	@set -e; \
	key="$${PA_KEY:-}"; \
	if [ -z "$$key" ]; then \
	  base="$$(echo '$(PA)' | sed -E 's/[0-9]+$$//')"; \
	  for cand in "$(KEYS_DIR)/$(PA)" "$$HOME/.ssh/id_ed25519_$(PA)" "$$HOME/.ssh/id_ed25519_$${base}"; do \
	    [ -f "$$cand" ] && key="$$cand" && break; \
	  done; \
	fi; \
	if [ -z "$$key" ] || [ ! -f "$$key" ]; then \
	  echo "PA key not found. Set PA_KEY or create one of: $(KEYS_DIR)/$(PA), $$HOME/.ssh/id_ed25519_$(PA), $$HOME/.ssh/id_ed25519_$${base}"; \
	  exit 1; \
	fi; \
	ssh -t -i "$$key" -p "$(PORT)" "$(PA)@localhost" '\
		set -e; \
		mkdir -p /shared_workspace/$(PROJ); cd /shared_workspace/$(PROJ); \
		claude || true \
	'

claude-doctor:
	@set -e; \
	key="$${PA_KEY:-}"; \
	if [ -z "$$key" ]; then \
	  base="$$(echo '$(PA)' | sed -E 's/[0-9]+$$//')"; \
	  for cand in "$(KEYS_DIR)/$(PA)" "$$HOME/.ssh/id_ed25519_$(PA)" "$$HOME/.ssh/id_ed25519_$${base}"; do \
	    [ -f "$$cand" ] && key="$$cand" && break; \
	  done; \
	fi; \
	if [ -z "$$key" ] || [ ! -f "$$key" ]; then \
	  echo "PA key not found. Set PA_KEY or create one of: $(KEYS_DIR)/$(PA), $$HOME/.ssh/id_ed25519_$(PA), $$HOME/.ssh/id_ed25519_$${base}"; \
	  exit 1; \
	fi; \
	ssh -t -i "$$key" -p "$(PORT)" "$(PA)@localhost" 'claude doctor || true'
