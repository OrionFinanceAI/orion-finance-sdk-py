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
	uv run ruff check --select I --fix ./
	uv run ruff format ./
	cd js && npm run prettier

.PHONY: docs
docs:
	uv run pydocstyle

.PHONY: test
test:
	uv run pytest -c pyproject.toml --cov=orion_finance_sdk_py --cov-report=xml --cov-report=term tests/
