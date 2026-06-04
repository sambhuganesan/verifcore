#ifndef CPP_KV_PARSER_H_
#define CPP_KV_PARSER_H_

#include <string>
#include <unordered_map>

using KeyValueMap = std::unordered_map<std::string, std::string>;

bool ParseKeyValueFields(const std::string& line,
                         const std::string& prefix,
                         KeyValueMap* fields,
                         std::string* error);

#endif  // CPP_KV_PARSER_H_