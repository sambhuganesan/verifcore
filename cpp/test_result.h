#ifndef CPP_TEST_RESULT_H_
#define CPP_TEST_RESULT_H_

#include <string>

struct TestResult {
    std::string suite;
    std::string test_name;
    int seed = 0;
    std::string worker_id;

    int cycles = 0;
    int expected_cycles = 0;
    double utilization = 0.0;

    std::string status;
    std::string failure_type;
    std::string assertion_name;
    std::string artifact_path;
};

std::string FormatTestResultSummary(const TestResult& result);

std::string TestResultToJson(const TestResult& result);

#endif  // CPP_TEST_RESULT_H_