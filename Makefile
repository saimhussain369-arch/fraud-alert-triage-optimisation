.PHONY: setup run test clean

setup:   ## create a virtual environment and install dependencies
	python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

run:     ## generate data, score, simulate, write outputs
	python run_pipeline.py

test:
	pytest -q

clean:
	rm -f data/*.duckdb data/alerts.csv
