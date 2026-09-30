.PHONY: help up down restart logs migrate revision test lint format shell seed clean

help:
	@echo "Available commands:"
	@echo "  make up          - Start all docker containers in background"
	@echo "  make down        - Stop all docker containers"
	@echo "  make restart     - Restart docker containers"
	@echo "  make logs        - Tail docker container logs"
	@echo "  make migrate     - Run database migrations"
	@echo "  make revision m=\"msg\" - Create a new alembic revision"
	@echo "  make test        - Run test suite with pytest"
	@echo "  make lint        - Run ruff and mypy linters"
	@echo "  make format      - Format code with ruff"
	@echo "  make shell       - Open bash shell in API container"
	@echo "  make seed        - Seed database with demo attacks, models and defenses"
	@echo "  make clean       - Remove python caches and temporary build files"

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f

migrate:
	docker compose exec api alembic upgrade head

revision:
	docker compose exec api alembic revision --autogenerate -m "$(m)"

test:
	pytest tests/ -v

lint:
	ruff check .
	mypy app/

format:
	ruff format .
	ruff check --fix .

shell:
	docker compose exec api bash

seed:
	docker compose exec api python -m scripts.seed

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
