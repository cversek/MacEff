SHELL := /bin/bash

PA       ?= maceff_user001
SID      ?= 001
PORT     ?= 2222
KEYS_DIR ?= keys
PA_KEY   ?= $(KEYS_DIR)/$(PA)
ADMIN_KEY?= $(KEYS_DIR)/admin

.PHONY: build up logs down mirror mirror-watch ssh-pa ssh-admin sa-test

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
	ssh -i $(PA_KEY) -p $(PORT) $(PA)@localhost

ssh-admin:
	ssh -i $(ADMIN_KEY) -p $(PORT) admin@localhost

sa-test:
	ssh -i $(PA_KEY) -p $(PORT) $(PA)@localhost '\
		set -euo pipefail; \
		P=$(PA); SID=$(SID); SA=sa_$${P}_$${SID}; \
		WD=/home/$${P}/agent/subagents/$${SID}; \
		LOG=$${WD}/public/logs/make-test.log; \
		sudo -n -u "$${SA}" /usr/local/bin/sa-exec "$${WD}" "$${LOG}" -- ":"; \
		sudo -n -u "$${SA}" /usr/local/bin/sa-exec "$${WD}" "$${LOG}" -- "echo from-make; id; whoami; pwd"; \
		sleep 0.2; tail -n 20 "$${LOG}" \
	'
