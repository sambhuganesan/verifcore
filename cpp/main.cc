#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

#include "line_reader.h"
#include "line_classifier.h"
#include "kv_parser.h"
#include "record_parser.h"
#include "test_result.h"

using std::cerr;
using std::cout;
using std::endl;
using std::string;
using std::vector;

void PrintFields(const KeyValueMap& fields) {
    for (const auto& entry : fields) {
        cout << "  " << entry.first << " = " << entry.second << '\n';
    }
}

int main(int argc, char** argv) {
    if (argc != 2) {
        cerr << "Usage: " << argv[0] << " <log_file>" << endl;
        return EXIT_FAILURE;
    }

    string input_path = argv[1];

    vector<string> lines;
    string error;

    if (!ReadNonEmptyLines(input_path, &lines, &error)) {
        cerr << "Error: " << error << endl;
        return EXIT_FAILURE;
    }

    vector<TestResult> results;

    if (!ParseTestResults(lines, &results, &error)) {
        cerr << "Error: " << error << endl;
        return EXIT_FAILURE;
    }

    for (const TestResult& result : results) {
        cout << TestResultToJson(result) << '\n';
    }
    return EXIT_SUCCESS;
}