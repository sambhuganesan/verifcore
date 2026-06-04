#include "test_result.h"

#include <string>
#include <sstream>

using std::string;

namespace {

std::string JsonEscape(const std::string& value) {
    std::string escaped;

    for (char c : value) {
        if (c == '\\') {
            escaped += "\\\\";
        } else if (c == '"') {
            escaped += "\\\"";
        } else if (c == '\n') {
            escaped += "\\n";
        } else if (c == '\r') {
            escaped += "\\r";
        } else if (c == '\t') {
            escaped += "\\t";
        } else {
            escaped += c;
        }
    }

    return escaped;
}

std::string JsonString(const std::string& value) {
    return "\"" + JsonEscape(value) + "\"";
}

}  // namespace


string FormatTestResultSummary(const TestResult& result) {
    string summary = "RESULT ";
    summary += result.suite;
    summary += ".";
    summary += result.test_name;
    summary += " seed=";
    summary += std::to_string(result.seed);
    summary += " status=";
    summary += result.status;
    summary += " cycles=";
    summary += std::to_string(result.cycles);

    if (result.status == "FAIL") {
        summary += " type=";
        summary += result.failure_type;
        summary += " assertion=";
        summary += result.assertion_name;
    }

    return summary;
}


std::string TestResultToJson(const TestResult& result) {
    std::ostringstream out;

    out << "{";
    out << "\"suite\":" << JsonString(result.suite) << ",";
    out << "\"test_name\":" << JsonString(result.test_name) << ",";
    out << "\"seed\":" << result.seed << ",";
    out << "\"worker_id\":" << JsonString(result.worker_id) << ",";
    out << "\"cycles\":" << result.cycles << ",";
    out << "\"expected_cycles\":" << result.expected_cycles << ",";
    out << "\"utilization\":" << result.utilization << ",";
    out << "\"status\":" << JsonString(result.status) << ",";
    out << "\"failure_type\":" << JsonString(result.failure_type) << ",";
    out << "\"assertion_name\":" << JsonString(result.assertion_name) << ",";
    out << "\"artifact_path\":" << JsonString(result.artifact_path);
    out << "}";

    return out.str();
}
