SHELL := /bin/bash

PA       ?= maceff_user001
SID      ?= 001
PORT     ?= 2222
KEYS_DIR ?= keys
PROJ     ?= demo

.PHONY: help init build build-deploy up logs down mirror mirror-watch ssh-pa ssh-admin sa-test claude claude-doctor test test-live

# Forward everything after the first goal as ARGS (and ignore a literal --)
RAW_ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
ARGS     := $(filter-out --,$(RAW_ARGS))
# Make those extra words no-op targets so make doesn't error
$(eval $(ARGS):;@:)

help:
	@echo "Targets:"
	@echo "  make init          - initialize .maceff/ structure (run once)"
	@echo "  make build         - build dev image (bind mounts)"
	@echo "  make build-deploy  - build deployment image (framework baked in)"
	@echo "  make up            - start services (detached)"
	@echo "  make logs          - follow logs"
	@echo "  make down          - stop services"
	@echo "  make mirror        - snapshot volumes -> sandbox-*"
	@echo "  make mirror-watch  - continuous mirroring (if enabled)"
	@echo "  make ssh-pa        - SSH into PA"
	@echo "  make ssh-admin     - SSH into admin"
	@echo "  make sa-test       - run a small SA job from the PA"
	@echo "  make claude        - launch Claude in /shared_workspace/\$(PROJ) (args forwarded)"
	@echo "  make claude-doctor - run 'claude doctor' inside the container"
	@echo "  make test            - run the hermetic pytest suite (macf/tests/, excludes -m live)"
	@echo "  make test-live       - run the live-external-state tests (macf/tests/, -m live: needs tmux/systemd/claude)"
	@echo "  make policy-sync     - sync framework/policies/<set> (default: base) into container & link current"
	@echo "  make policy-sync-SET - sync framework/policies/SET (e.g., policy-sync-base)"
	@echo "  make template-sync   - sync framework/templates/ into container"
	@echo "  make assets-sync     - sync framework/{commands,skills,subagents,output-styles}/"
	@echo "  make framework-upgrade - run every sync step, then upgrade preambles"

build:
	maceff_tools/compose build

up:
	maceff_tools/compose up -d

logs:
	maceff_tools/compose logs -f --tail=120

down:
	maceff_tools/compose down

mirror:
	maceff_tools/compose --profile mirror up --no-deps mirror

mirror-watch:
	maceff_tools/compose --profile mirror-watch up mirror-watch

ssh-pa:
	maceff_tools/ssh-pa

ssh-admin:
	maceff_tools/ssh-admin

sa-test:
	maceff_tools/sa-test

claude:
	maceff_tools/claude-remote $(ARGS)

claude-doctor:
	maceff_tools/claude-doctor

.PHONY: policy-sync policy-sync-% template-sync assets-sync framework-upgrade

policy-sync:
	maceff_tools/policy-sync

policy-sync-%:
	maceff_tools/policy-sync $*

template-sync:
	maceff_tools/template-sync

assets-sync:
	maceff_tools/assets-sync

framework-upgrade:
	maceff_tools/framework-upgrade

init:
	maceff_tools/maceff-init

test:
	pytest macf/tests/ -x -q -m "not live"

test-live:
	pytest macf/tests/ -x -q -m "live"

build-deploy:
	@echo "Building deployment image (framework baked in)..."
	docker build -f docker/Dockerfile.deploy -t maceff-deploy:latest .
