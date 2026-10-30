.PHONY: setup web test qa build demo run contract

setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install -e '.[dev]'
	npm --prefix web ci

web:
	npm --prefix web run build

test:
	.venv/bin/python -m ruff check backend tests scripts
	.venv/bin/python -m pytest -q
	npm --prefix web run typecheck

qa: web
	npm --prefix web run test:e2e

build:
	.venv/bin/python scripts/build_app.py

demo: web
	PYTHONPATH=backend .venv/bin/python -m itunesremote --demo --data-dir .local/demo --open-browser

run: web
	PYTHONPATH=backend .venv/bin/python -m itunesremote --open-browser

contract:
	.venv/bin/python scripts/export_openapi.py
