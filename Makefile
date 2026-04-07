UV := uv

.PHONY: install lint format typecheck test run

install:
	$(UV) sync --dev

lint:
	$(UV) run ruff check .

format:
	$(UV) run ruff format .

typecheck:
	$(UV) run mypy src tests

test:
	$(UV) run pytest

run:
	$(UV) run uvicorn air_platform.service.app:app --reload

