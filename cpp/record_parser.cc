#include "record_parser.h"
#include "line_classifier.h"
#include "kv_parser.h"

#include <string>
#include <vector>


bool ParseTestResults(const std::vector<std::string>& lines,
                      std::vector<TestResult>* results,
                      std::string* error) {
    if (results == nullptr) {
        if (error != nullptr) {
            *error = "result pointer is null";
        }
        return false;
    }
    results->clear();

    TestResult current;
    bool have_run = false;
    bool have_metric = false;

    for (const std::string& line : lines) {
        LineKind kind = ClassifyLine(line);

        if (kind == LineKind::RUN) {
            if (have_run) {
                if (error != nullptr) {
                    *error = "test has not finished";
                }
                return false;
            }

            KeyValueMap fields;
            if (!ParseKeyValueFields(line, "[RUN] ", &fields, error)) {
                return false;
            }

            current = TestResult{};
            current.suite = fields["suite"];
            current.test_name = fields["test"];
            current.seed = std::stoi(fields["seed"]);
            current.worker_id = fields["worker"];

            have_run = true;
            have_metric = false;
        } else if (kind == LineKind::METRIC) {
            if (!have_run) {
                if (error != nullptr) {
                    *error = "saw METRIC before RUN";
                }
                return false;
            }

            if (have_metric) {
                if (error != nullptr) {
                    *error = "duplicate METRIC line for one test";
                }
                return false;
            }

            KeyValueMap fields;
            if (!ParseKeyValueFields(line, "[METRIC] ", &fields, error)) {
                return false;
            }

            current.cycles = std::stoi(fields["cycles"]);
            current.expected_cycles = std::stoi(fields["expected_cycles"]);
            current.utilization = std::stod(fields["utilization"]);

            have_metric = true;
        } else if (kind == LineKind::PASS) {
            if (!have_run || !have_metric) {
                if (error != nullptr) {
                    *error = "saw PASS before complete RUN/METRIC";
                }
                return false;
            }

            current.status = "PASS";
            current.failure_type = "none";
            current.assertion_name = "none";
            current.artifact_path = "";

            results->push_back(current);

            current = TestResult{};
            have_run = false;
            have_metric = false;
        } else if (kind == LineKind::FAIL) {
            if (!have_run || !have_metric) {
                if (error != nullptr) {
                    *error = "saw FAIL before complete RUN/METRIC record";
                }
                return false;
            }

            KeyValueMap fields;
            if (!ParseKeyValueFields(line, "[FAIL] ", &fields, error)) {
                return false;
            }

            current.status = "FAIL";
            current.failure_type = fields["type"];
            current.assertion_name = fields["assertion"];
            current.artifact_path = fields["artifact"];

            results->push_back(current);

            current = TestResult{};
            have_run = false;
            have_metric = false;
        } else {
            if (error != nullptr) {
                *error = "unknown line type";
            }
            return false;
        }

    }

    if (have_run || have_metric) {
        if (error != nullptr) {
            *error = "file ended before current test completed";
        }
        return false;
    }

    return true;

}