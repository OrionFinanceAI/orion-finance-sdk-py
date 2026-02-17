.PHONY: uv-download
uv-download:
	@command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh

.PHONY: venv
venv:
	rm -rf .venv build dist *.egg-info
	rm -rf abis/
	uv venv --python 3.13

.PHONY: install
install:
	uv pip install -e ."[dev]"
	uv run pre-commit install
	cd js && npm install && npm run build
	./scripts/build_js.sh

.PHONY: codestyle
codestyle:
	uv run ruff format
	uv run ruff check --select I --fix

	cd js && npm run prettier

.PHONY: docstyle
docstyle:
	uv run pydocstyle

.PHONY: docs
docs:
	uv run sphinx-build -b html docs docs/_build/html

.PHONY: open-docs
open-docs:
	open docs/_build/html/index.html || xdg-open docs/_build/html/index.html

.PHONY: test
test:
	@if [ -z "$$CI" ]; then uv sync --extra dev; fi
	uv run pytest -c pyproject.toml --cov=orion_finance_sdk_py --cov-report=xml --cov-report=term tests/

.PHONY: sepolia-fork
sepolia-fork:
	uv run ape test tests/test_fork.py --network ethereum:sepolia-fork:hardhat -s
