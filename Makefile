# See: https://www.gnu.org/software/make/manual/make.html

PDOC = pydoctor --make-html --docformat="plaintext" --disable-intersphinx-cache --project-name "Dycco" --html-output
DYCCO = dycco --output-dir=docs --escape-html

setup:
	uv sync


.PHONY: documentation
documentation:
	uv run $(PDOC) docs/api src/dycco
	uv run $(DYCCO) src/dycco/*.py

# Call 'make clean' to get rid of the documentation directory's html entries
# No directory or file will be called 'clean' so mark it as a phony
.PHONY: clean
clean:
	rm -rf docs/api/*
	rm -rf docs/*
	rm -rf dist/*

# Run from top-level directory. Creates a pytest html report and a coverage report (in htmlcov)
test:
	uv run pytest -s  --html PyTest_Report.html --cov=./ --cov-report html --log-cli-level=DEBUG
