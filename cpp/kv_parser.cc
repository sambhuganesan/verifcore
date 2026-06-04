#include "kv_parser.h"

#include <sstream>

#include "string_utils.h"

using std::string;
using std::istringstream;

bool ParseKeyValueFields(const std::string& line,
                         const std::string& prefix,
                         KeyValueMap* fields,
                         std::string* error) {
    if (fields == nullptr) {
        return false;
    }

    fields->clear();

    if (!StartsWith(line, prefix)) {
        if (error != nullptr) {
            *error = "line doesn't start with expected prefix";
        }
        return false;
    }

    string body = line.substr(prefix.size());
    istringstream iss(body);
    string token;

    while (iss >> token) {
        size_t equal_pos = token.find('=');
        if (equal_pos == string::npos) {
            if (error != nullptr) {
                *error = "token is missing '=': " + token;
            }
            return false;
        }

        string key = token.substr(0, equal_pos);
        string val = token.substr(equal_pos + 1);

        if (key.empty() || val.empty()) {
            if (error != nullptr) {
                *error = "line doesn't have key and/or val: " + token;
            }
            return false;
        }

        (*fields)[key] = val;
    }

    return true;
}
