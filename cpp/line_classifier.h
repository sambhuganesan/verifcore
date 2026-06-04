#ifndef CPP_LINE_CLASSIFIER_H_
#define CPP_LINE_CLASSIFIER_H_

#include <string>

enum class LineKind {
    RUN,
    METRIC,
    PASS,
    FAIL,
    UNKNOWN
};

LineKind ClassifyLine(const std::string& line);

std::string LineKindToString(LineKind kind);

#endif