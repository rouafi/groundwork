.PHONY: setup lint typecheck arch test test-int check demo live evals up down

setup:        ## Install deps and git hooks
	uv sync
	uv run pre-commit install

lint:         ## Lint and format check
	uv run ruff check .
	uv run ruff format --check .

typecheck:    ## Strict typing
	uv run mypy

arch:         ## Architecture rules (core never imports adapters)
	uv run lint-imports

test:         ## Unit + contract tests with coverage on core
	uv run pytest -m "unit or contract" --cov --cov-report=term-missing

test-int:     ## Integration tests (no paid API)
	uv run pytest -m integration

check: lint typecheck arch test test-int  ## Everything CI runs
	uv run groundwork validate-packs
	uv run groundwork evals --check-report --allow-unmet-thresholds

demo:         ## Replay recorded runs, no API key needed
	GROUNDWORK_MODEL=replay uv run groundwork demo

live:         ## Real run with Claude (needs .env)
	GROUNDWORK_MODEL=claude uv run --env-file .env groundwork demo --model claude

evals:        ## Run the golden sets for every client pack
	uv run groundwork evals

up:           ## Start API and MCP server
	docker compose up --build -d

down:
	docker compose down
