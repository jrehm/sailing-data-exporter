.PHONY: install run freeze test lint

install:
	python3 -m venv venv
	./venv/bin/pip install -r requirements.txt -e ".[dev]"

run:
	./venv/bin/python app.py

freeze:
	./venv/bin/pip freeze > requirements.txt

test:
	./venv/bin/python -m pytest

lint:
	./venv/bin/ruff check .
