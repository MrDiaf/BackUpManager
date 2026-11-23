.DEFAULT_GOAL := help
COMPOSE := docker compose
SERVICE := backupmanager
PORT ?= $(shell grep -s '^PORT=' .env | cut -d= -f2)
LAN_IP := $(shell hostname -I 2>/dev/null | awk '{print $$1}')
URLS := Web UI: http://127.0.0.1:$(or $(PORT),8095)  (on the network: http://$(LAN_IP):$(or $(PORT),8095))

.PHONY: help up down restart logs status password test check-docker

help: ## Show this help
	@echo "Available commands:"
	@echo
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-9s %s\n", $$1, $$2}'

check-docker:
	@command -v docker >/dev/null 2>&1 || { echo "Docker is required to run this project. Install Docker and retry 'make up'."; exit 1; }
	@docker compose version >/dev/null 2>&1 || { echo "Docker Compose v2 ('docker compose') is required. Install it and retry."; exit 1; }
	@docker info >/dev/null 2>&1 || { echo "Cannot reach the Docker daemon. Is it running, and is your user in the 'docker' group?"; exit 1; }

up: check-docker ## Build and start the backup manager
	@mkdir -p data
	$(COMPOSE) up -d --build
	@echo "Waiting for the web UI..."
	@for i in $$(seq 1 30); do \
	  $(COMPOSE) exec -T $(SERVICE) python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8095/health')" >/dev/null 2>&1 \
	    && { echo; echo "Backup manager is running."; echo; echo "$(URLS)"; echo "Login: any username, password from 'make password'"; echo; echo "Run 'make help' for available commands."; exit 0; }; \
	  sleep 1; \
	done; echo "The web UI did not come up. See 'make logs'."; exit 1

down: ## Stop the backup manager (jobs, history and backups are kept)
	$(COMPOSE) down

restart: ## Restart the backup manager
	$(COMPOSE) restart

logs: ## Follow the application logs
	$(COMPOSE) logs -f

status: ## Show whether the container is running
	$(COMPOSE) ps

password: ## Show the web UI password
	@if grep -qs '^UI_PASSWORD=..*' .env; then echo "The password is UI_PASSWORD in .env."; \
	else $(COMPOSE) exec -T $(SERVICE) cat /data/ui-password || echo "Start the app first ('make up')."; fi

test: check-docker ## Run the unit tests inside the container image
	$(COMPOSE) build -q
	$(COMPOSE) run --rm --no-deps -T --entrypoint python $(SERVICE) -m unittest discover -s /app/tests -v
