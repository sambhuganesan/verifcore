#include "line_reader.h"

#include <fcntl.h>
#include <unistd.h>

#include <string>
#include <vector>

using std::string;
using std::vector;

namespace {

// Normalize CRLF input so lines do not keep a trailing '\r'.
void StripTrailingCarriageReturn(string* line) {
    if (!line->empty() && line->back() == '\r') {
        line->pop_back();
    }
}

void PushCleanLine(string* line, vector<string>* lines) {
    StripTrailingCarriageReturn(line);

    if (!line->empty()) {
        lines->push_back(*line);
    }
}

}  // namespace

bool ReadNonEmptyLines(const string& input_path,
                       vector<string>* lines,
                       string* error) {
    if (lines == nullptr) {
        if (error != nullptr) {
            *error = "ReadNonEmptyLines received null lines pointer";
        }
        return false;
    }

    lines->clear();

    int fd = open(input_path.c_str(), O_RDONLY);
    if (fd == -1) {
        if (error != nullptr) {
            *error = "could not open " + input_path;
        }
        return false;
    }

    string pending;
    char buf[4096];

    // Keep unprocessed bytes in pending so lines split across reads are preserved.
    while (true) {
        ssize_t bytes_read = read(fd, buf, sizeof(buf));

        if (bytes_read == -1) {
            if (error != nullptr) {
                *error = "error while reading " + input_path;
            }
            close(fd);
            return false;
        }

        if (bytes_read == 0) {
            break;
        }

        pending.append(buf, bytes_read);

        size_t newline_pos = pending.find('\n');
        while (newline_pos != string::npos) {
            string line = pending.substr(0, newline_pos);
            pending.erase(0, newline_pos + 1);

            PushCleanLine(&line, lines);

            newline_pos = pending.find('\n');
        }
    }

    // Handle the final line even when the file does not end with '\n'.
    if (!pending.empty()) {
        PushCleanLine(&pending, lines);
    }

    close(fd);
    return true;
}