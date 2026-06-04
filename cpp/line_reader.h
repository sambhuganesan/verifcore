#ifndef CPP_LINE_READER_H_
#define CPP_LINE_READER_H_

#include <string>
#include <vector>

// Reads input_path using low-level Unix read(), reconstructs full lines,
// normalizes Windows CRLF by stripping trailing '\r', skips empty lines,
// and stores the cleaned lines in `lines`.
//
// Returns true on success.
// Returns false on failure and writes a human-readable message to `error`.
bool ReadNonEmptyLines(const std::string& input_path,
                       std::vector<std::string>* lines,
                       std::string* error);

#endif  // CPP_LINE_READER_H_