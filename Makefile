# PVR Agent Room. On Windows without make, use the scripts in scripts\ (see README.md).
# Recipes below use POSIX shell paths (macOS, Linux, or Git Bash with make installed).

PYTHON ?= python3
VENV   := backend/.venv
VPY    := $(VENV)/bin/python
ifeq ($(OS),Windows_NT)
VPY    := $(VENV)/Scripts/python.exe
endif
CHANGE ?= wall_height

.PHONY: setup dev backend frontend test test-live check-llm cli-engines cli-run

setup:          ## backend venv + deps, frontend npm install
	test -x $(VPY) || $(PYTHON) -m venv $(VENV)
	$(VPY) -m pip install --upgrade pip
	$(VPY) -m pip install -e "backend[dev]"
	cd frontend && npm ci

dev:            ## backend on :8000, frontend on :5173
	$(MAKE) -j2 backend frontend

backend:
	cd backend && ../$(VPY) -m uvicorn pvr.api.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir pvr

frontend:
	cd frontend && npm run dev

test:           ## pytest (excluding live) + vitest
	cd backend && ../$(VPY) -m pytest -m "not live"
	cd frontend && npm run typecheck && npm run test

test-live:      ## live tests with OPENAI_API_KEY
	cd backend && ../$(VPY) -m pytest -m live

check-llm:      ## confirm the OpenAI key and that OPENAI_MODEL supports tool calling
	cd backend && ../$(VPY) -m pvr.cli check-llm

cli-engines:    ## deterministic report for all three defaults, no LLM (from Phase 1)
	cd backend && ../$(VPY) -m pvr.cli engines

cli-run:        ## full agent run in the console with an approval prompt (from Phase 3)
	cd backend && ../$(VPY) -m pvr.cli run --change $(CHANGE)
