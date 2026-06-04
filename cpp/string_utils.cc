#include "string_utils.h"

bool StartsWith(const std::string& s, const std::string& prefix) {
    return s.rfind(prefix, 0) == 0;
}
