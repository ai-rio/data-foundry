.PHONY: help install install-dev test lint format type-check clean run docs

# Default target
help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Installation
install: ## Install production dependencies
	uv sync

install-dev: ## Install development dependencies
	uv sync --dev

# Code Quality
lint: ## Run linting checks
	uv run ruff check src/ tests/

format: ## Format code with Black and ruff
	uv run black src/ tests/
	uv run ruff format src/ tests/
	uv run isort src/ tests/

format-black: ## Format code with Black only
	uv run black src/ tests/

format-ruff: ## Format code with ruff only
	uv run ruff format src/ tests/

format-check: ## Check if code is formatted
	uv run black --check src/ tests/
	uv run ruff format --check src/ tests/
	uv run isort --check-only src/ tests/

type-check: ## Run type checking with mypy
	uv run mypy src/

# Testing
test: ## Run all tests
	uv run pytest

test-cov: ## Run tests with coverage
	uv run pytest --cov=src --cov-report=html

test-unit: ## Run unit tests only
	uv run pytest tests/unit/

test-integration: ## Run integration tests only
	uv run pytest tests/integration/

test-api: ## Run API tests only
	uv run pytest tests/api/

test-fast: ## Run fast tests (exclude slow)
	uv run pytest -m "not slow"

# Development
run: ## Run the FastAPI application
	uv run python -m src.main

dev: ## Run the FastAPI application with reload
	uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Docker
docker-up: ## Start all services with Docker
	docker compose up -d

docker-down: ## Stop all Docker services
	docker compose down

docker-logs: ## Show Docker logs
	docker compose logs -f

# Database
db-reset: ## Reset the database
	docker compose down db
	docker volume rm data_foundry_postgres_data || true
	docker compose up -d db

# Documentation
docs: ## Generate API documentation
	uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload &
	sleep 2
	@echo "API docs available at http://localhost:8000/docs"
	@echo "ReDoc available at http://localhost:8000/redoc"

# CI/CD
ci: format-check lint type-check test ## Run full CI pipeline (format-check, lint, type-check, test)

# Cleanup
clean: ## Clean up cache and build artifacts
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	rm -rf .coverage htmlcov/ .pytest_cache/ .mypy_cache/
	rm -rf dist/ build/ *.egg-info/

# Setup
setup: install-dev ## Set up the development environment
	uv run pre-commit install

# All
all: format lint type-check test ## Run all code quality checks and tests