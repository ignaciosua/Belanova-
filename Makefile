SHELL := /bin/bash

VENV ?= .venv
PYTHON ?= python3
VENV_PY := $(VENV)/bin/python
BELANOVA_BIN := $(VENV)/bin/belanova
BELANOVA_DOCTOR_BIN := $(VENV)/bin/belanova-doctor
BELANOVA_TTS_TEST_BIN := $(VENV)/bin/belanova-tts-test

.PHONY: help setup setup-system setup-client sync-skills sync-skills-all run doctor tts-test install-skill-deps

help:
	@echo "Targets disponibles:"
	@echo "  make setup         -> instala deps + skill-bridge + mcp.json"
	@echo "  make setup-system  -> setup + paquetes del sistema via apt-get"
	@echo "  make setup-client  -> setup 1 comando para Linux cliente"
	@echo "  make sync-skills   -> trae solo skills core al workspace"
	@echo "  make sync-skills-all -> trae todas las skills detectadas"
	@echo "  make run           -> ejecuta belanova runtime"
	@echo "  make doctor        -> ejecuta diagnóstico"
	@echo "  make tts-test      -> prueba rápida de TTS"
	@echo "  make install-skill-deps -> instala requirements de skills"

setup:
	bash scripts/install_all.sh

setup-system:
	bash scripts/install_all.sh --install-system-deps

setup-client:
	bash scripts/client_linux_install.sh

sync-skills:
	$(PYTHON) scripts/sync_workspace_skills.py --overwrite

sync-skills-all:
	$(PYTHON) scripts/sync_workspace_skills.py --overwrite --profile all

run:
	@if [ -x "$(BELANOVA_BIN)" ]; then \
		$(BELANOVA_BIN); \
	elif command -v belanova >/dev/null 2>&1; then \
		belanova; \
	else \
		PYTHONPATH=src $(PYTHON) -m belanova.app.runtime; \
	fi

doctor:
	@if [ -x "$(BELANOVA_DOCTOR_BIN)" ]; then \
		$(BELANOVA_DOCTOR_BIN); \
	elif command -v belanova-doctor >/dev/null 2>&1; then \
		belanova-doctor; \
	else \
		PYTHONPATH=src $(PYTHON) -m belanova.app.diagnostics; \
	fi

tts-test:
	@if [ -x "$(BELANOVA_TTS_TEST_BIN)" ]; then \
		$(BELANOVA_TTS_TEST_BIN); \
	elif command -v belanova-tts-test >/dev/null 2>&1; then \
		belanova-tts-test; \
	else \
		PYTHONPATH=src $(PYTHON) -m belanova.app.tts_test; \
	fi

install-skill-deps:
	@if [ -x "$(VENV_PY)" ]; then \
		MCP_CONFIG_PATH=$${MCP_CONFIG_PATH:-$$HOME/.config/Code/User/mcp.json} $(VENV_PY) ensure_skill_deps.py; \
	else \
		MCP_CONFIG_PATH=$${MCP_CONFIG_PATH:-$$HOME/.config/Code/User/mcp.json} $(PYTHON) ensure_skill_deps.py; \
	fi
