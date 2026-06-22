CXX ?= g++
CXXFLAGS ?= -std=c++17 -Wall -Wextra -O2
PYTHON ?= python3
STREAMLIT_PYTHON ?= .venv/bin/python
NUM_TESTS ?= 1000
NUM_RUNS ?= 4

CPP_SRCS := $(sort $(wildcard cpp/*.cc))
LOG_PARSER := log_parser
DB := verifcore.db

.PHONY: build generate-baseline generate-regression generate-runs parse ingest analyze test ui demo clean

build:
	$(CXX) $(CXXFLAGS) $(CPP_SRCS) -o $(LOG_PARSER)

generate-baseline:
	$(PYTHON) -m backend.generate_logs --out sample_logs/run_001.log --seed 1 --num-tests $(NUM_TESTS)

generate-regression:
	$(PYTHON) -m backend.generate_logs --out sample_logs/run_002.log --seed 2 --num-tests $(NUM_TESTS) --inject-regressions

generate-runs:
	@if [ "$(NUM_RUNS)" -lt 2 ]; then echo "NUM_RUNS must be at least 2"; exit 1; fi
	mkdir -p sample_logs
	$(PYTHON) -m backend.generate_logs --out sample_logs/run_001.log --seed 1 --num-tests $(NUM_TESTS)
	@i=2; while [ $$i -le $(NUM_RUNS) ]; do \
		run_name=$$(printf "run_%03d" $$i); \
		$(PYTHON) -m backend.generate_logs --out sample_logs/$$run_name.log --seed $$i --num-tests $(NUM_TESTS) --inject-regressions; \
		i=$$((i + 1)); \
	done

parse:
	mkdir -p parsed
	@i=1; while [ $$i -le $(NUM_RUNS) ]; do \
		run_name=$$(printf "run_%03d" $$i); \
		./$(LOG_PARSER) sample_logs/$$run_name.log > parsed/$$run_name.jsonl; \
		i=$$((i + 1)); \
	done

ingest:
	@i=1; while [ $$i -le $(NUM_RUNS) ]; do \
		run_name=$$(printf "run_%03d" $$i); \
		commit_hash=$$(printf "commit_%03d" $$i); \
		$(PYTHON) -m backend.ingest --db $(DB) --run-name $$run_name --commit $$commit_hash parsed/$$run_name.jsonl; \
		i=$$((i + 1)); \
	done

analyze:
	$(PYTHON) -m backend.analyze --db $(DB) --baseline run_001 --current run_002

test:
	$(PYTHON) -m pytest tests

ui:
	STREAMLIT_BROWSER_GATHER_USAGE_STATS=false $(STREAMLIT_PYTHON) -m streamlit run ui/app.py --server.headless true

demo:
	$(MAKE) clean
	$(MAKE) build
	$(MAKE) generate-runs NUM_TESTS=$(NUM_TESTS) NUM_RUNS=$(NUM_RUNS)
	$(MAKE) parse NUM_RUNS=$(NUM_RUNS)
	$(MAKE) ingest NUM_RUNS=$(NUM_RUNS)
	$(MAKE) analyze

clean:
	rm -f $(LOG_PARSER)
	rm -f $(DB)
	rm -f parsed/*.jsonl
	rm -f sample_logs/run_*.log
