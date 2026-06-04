CXX ?= g++
CXXFLAGS ?= -std=c++17 -Wall -Wextra -O2
PYTHON ?= python3
STREAMLIT_PYTHON ?= .venv/bin/python
NUM_TESTS ?= 200

CPP_SRCS := $(sort $(wildcard cpp/*.cc))
LOG_PARSER := log_parser
DB := verifcore.db

.PHONY: build generate-baseline generate-regression parse ingest analyze test ui demo clean

build:
	$(CXX) $(CXXFLAGS) $(CPP_SRCS) -o $(LOG_PARSER)

generate-baseline:
	$(PYTHON) -m backend.generate_logs --out sample_logs/run_001.log --seed 1 --num-tests $(NUM_TESTS)

generate-regression:
	$(PYTHON) -m backend.generate_logs --out sample_logs/run_002.log --seed 2 --num-tests $(NUM_TESTS) --inject-regressions

parse:
	mkdir -p parsed
	./$(LOG_PARSER) sample_logs/run_001.log > parsed/run_001.jsonl
	./$(LOG_PARSER) sample_logs/run_002.log > parsed/run_002.jsonl

ingest:
	$(PYTHON) -m backend.ingest --db $(DB) --run-name run_001 --commit abc123 parsed/run_001.jsonl
	$(PYTHON) -m backend.ingest --db $(DB) --run-name run_002 --commit def456 parsed/run_002.jsonl

analyze:
	$(PYTHON) -m backend.analyze --db $(DB) --baseline run_001 --current run_002

test:
	$(PYTHON) -m pytest tests

ui:
	STREAMLIT_BROWSER_GATHER_USAGE_STATS=false $(STREAMLIT_PYTHON) -m streamlit run ui/app.py --server.headless true

demo:
	$(MAKE) clean
	$(MAKE) build
	$(MAKE) generate-baseline
	$(MAKE) generate-regression
	$(MAKE) parse
	$(MAKE) ingest
	$(MAKE) analyze

clean:
	rm -f $(LOG_PARSER)
	rm -f $(DB)
	rm -f parsed/*.jsonl
	rm -f sample_logs/run_*.log
