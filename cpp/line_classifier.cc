#include "line_classifier.h"

#include <string>

#include "string_utils.h"

using std::string;

LineKind ClassifyLine(const string& line) {
    if (StartsWith(line, "[RUN] ")) {
        return LineKind::RUN;
    }

    if (StartsWith(line, "[METRIC] ")) {
        return LineKind::METRIC;
    }

    if (line == "[PASS]") {
        return LineKind::PASS;
    }

    if (StartsWith(line, "[FAIL] ")) {
        return LineKind::FAIL;
    }

    return LineKind::UNKNOWN;
}

string LineKindToString(LineKind kind) {
    switch (kind) {
        case LineKind::RUN:
            return "RUN";
        case LineKind::METRIC:
            return "METRIC";
        case LineKind::PASS:
            return "PASS";
        case LineKind::FAIL:
            return "FAIL";
        case LineKind::UNKNOWN:
            return "UNKNOWN";
    }

    return "UNKNOWN";
}
