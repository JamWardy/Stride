.PHONY: install dev api web types test lint

API_PORT ?= 8000

install:  ## Install Python and frontend dependencies
	uv sync
	npm --prefix apps/web install

dev:  ## Run the API and the web app together; Ctrl-C stops both
	@trap 'kill 0' INT TERM EXIT; \
	$(MAKE) --no-print-directory api & \
	$(MAKE) --no-print-directory web & \
	wait

api:
	uv run uvicorn speedy_api.main:app --reload --port $(API_PORT)

web:
	npm --prefix apps/web run dev

types:  ## Regenerate the frontend's API types from FastAPI's OpenAPI schema
	uv run python -m speedy_api.export_openapi apps/web/openapi.json
	npm --prefix apps/web run gen:api

test:
	uv run pytest
	npm --prefix apps/web test

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	npm --prefix apps/web run typecheck
