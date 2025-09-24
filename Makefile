SHELL := /bin/bash

PA       ?= maceff_user001
SID      ?= 001
PORT     ?= 2222
KEYS_DIR ?= keys
PROJ     ?= demo

.PHONY: help build up logs down mirror mirror-watch ssh-pa ssh-admin sa-test claude claude-doctor

# Forward everything after the first goal as ARGS (and ignore a literal --)
RAW_ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
ARGS     := $(filter-out --,$(RAW_ARGS))
# Make those extra words no-op targets so make doesn't error
$(eval $(ARGS):;@:)

help:
	@echo "Targets:"
	@echo "  make build         - docker compose build"
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

build:
	tools/bin/compose build

up:
	tools/bin/compose up -d

logs:
	tools/bin/compose logs -f --tail=120

down:
	tools/bin/compose down

mirror:
	tools/bin/compose --profile mirror up --no-deps mirror

mirror-watch:
	tools/bin/compose --profile mirror-watch up mirror-watch

ssh-pa:
	tools/bin/ssh-pa

ssh-admin:
	tools/bin/ssh-admin

sa-test:
	tools/bin/sa-test

claude:
	tools/bin/claude-remote $(ARGS)

claude-doctor:
	tools/bin/claude-doctor
