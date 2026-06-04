#ifndef CPP_RECORD_PARSER_H_
#define CPP_RECORD_PARSER_H_

#include <string>
#include <vector>

#include "test_result.h"

bool ParseTestResults(const std::vector<std::string>& lines,
                      std::vector<TestResult>* results,
                      std::string* error);

#endif  // CPP_RECORD_PARSER_H_