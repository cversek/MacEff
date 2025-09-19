SHELL := /bin/bash

PA       ?= maceff_user001
SID      ?= 001
PORT     ?= 2222
KEYS_DIR ?= keys

# Default/fallback private keys
HOME_SSH            := $(HOME)/.ssh
DEFAULT_PA_PRIV     := $(HOME_SSH)/id_ed25519_$(PA)
DEFAULT_ADMIN_PRIV  := $(HOME_SSH)/id_ed25519_admin

# Prefer keys/<name> if present; else fall back to ~/.ssh
PA_KEY    ?= $(shell [ -f "$(KEYS_DIR)/$(PA)" ] && printf "$(KEYS_DIR)/$(PA)" || ([ -f "$(DEFAULT_PA_PRIV)" ] && printf "$(DEFAULT_PA_PRIV)" || printf ""))
ADMIN_KEY ?= $(shell [ -f "$(KEYS_DIR)/admin" ] && printf "$(KEYS_DIR)/admin" || ([ -f "$(DEFAULT_ADMIN_PRIV)" ] && printf "$(DEFAULT_ADMIN_PRIV)" || printf ""))

.PHONY: help build up logs down mirror mirror-watch ssh-pa ssh-admin sa-test

help:
	@echo "Targets:"
	@echo "  make build        - docker-compose build"
	@echo "  make up           - start services"
	@echo "  make logs         - follow logs"
	@echo "  make down         - stop services"
	@echo "  make mirror       - snapshot volumes -> sandbox-*"
	@echo "  make mirror-watch - continuous mirror (if enabled)"
	@echo "  make ssh-pa       - SSH into PA (override PA=..., PA_KEY=...)"
	@echo "  make ssh-admin    - SSH into admin (override ADMIN_KEY=...)"
	@echo "  make sa-test      - run a small SA job from the PA"

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
	@if [ -z "$(PA_KEY)" ] || [ ! -f "$(PA_KEY)" ]; then \
	  echo "PA_KEY not found. Provide a private key via PA_KEY=... (e.g. ~/.ssh/id_ed25519_$(PA))"; exit 1; \
	fi
	ssh -i "$(PA_KEY)" -p "$(PORT)" "$(PA)@localhost"

ssh-admin:
	@if [ -z "$(ADMIN_KEY)" ] || [ ! -f "$(ADMIN_KEY)" ]; then \
	  echo "ADMIN_KEY not found. Provide a private key via ADMIN_KEY=... (e.g. ~/.ssh/id_ed25519_admin)"; exit 1; \
	fi
	ssh -i "$(ADMIN_KEY)" -p "$(PORT)" admin@localhost

sa-test:
	@if [ -z "$(PA_KEY)" ] || [ ! -f "$(PA_KEY)" ]; then \
	  echo "PA_KEY not found. Provide PA_KEY=... (e.g. ~/.ssh/id_ed25519_$(PA))"; exit 1; \
	fi
	ssh -i "$(PA_KEY)" -p "$(PORT)" "$(PA)@localhost" '\
		set -euo pipefail; \
		P=$(PA); SID=$(SID); SA=sa_$${P}_$${SID}; \
		WD=/home/$${P}/agent/subagents/$${SID}; \
		LOG=$${WD}/public/logs/make-test.log; \
		sudo -n -u "$${SA}" /usr/local/bin/sa-exec "$${WD}" "$${LOG}" -- ":"; \
		sudo -n -u "$${SA}" /usr/local/bin/sa-exec "$${WD}" "$${LOG}" -- "echo from-make; id; whoami; pwd"; \
		sleep 0.2; tail -n 20 "$${LOG}" \
	'
