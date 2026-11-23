# Run `just` to list recipes.

api_port := env("API_PORT", "8000")

# List recipes
default:
    @just --list

# Install Python and frontend dependencies
install:
    uv sync
    npm --prefix apps/web install

# Run the API and the web app together; Ctrl-C stops both
[no-exit-message]
dev:
    #!/usr/bin/env bash
    trap 'kill 0' INT TERM EXIT
    just api &
    just web &
    wait

# Run the API on its own (port from API_PORT, default 8000)
api:
    uv run uvicorn stride_api.main:app --reload --port {{api_port}}

# Run the web app on its own
web:
    npm --prefix apps/web run dev

# Regenerate the frontend's API types from FastAPI's OpenAPI schema
types:
    uv run python -m stride_api.export_openapi apps/web/openapi.json
    npm --prefix apps/web run gen:api

# Run the Python and frontend tests
test:
    uv run pytest
    npm --prefix apps/web test

# Lint, format-check and type-check everything
lint:
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy
    npm --prefix apps/web run typecheck
