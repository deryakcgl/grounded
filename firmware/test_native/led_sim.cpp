#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <chrono>

#include "led_device.h"

static void write_stdout(const char* text, size_t len) {
  fwrite(text, 1, len, stdout);
  fflush(stdout);
}

int main(int argc, char** argv) {
  double speed = 1.0;
  if (argc == 3 && strcmp(argv[1], "--speed") == 0) speed = atof(argv[2]);
  if (speed <= 0) {
    fprintf(stderr, "usage: %s [--speed N]\n", argv[0]);
    return 2;
  }

  const auto t0 = std::chrono::steady_clock::now();
  auto now_ms = [&]() -> uint32_t {
    const double real_ms =
        std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
    return (uint32_t)(real_ms * speed);
  };

  LedDevice device(write_stdout);
  device.begin();

  for (;;) {
    struct pollfd pfd = {STDIN_FILENO, POLLIN, 0};
    if (poll(&pfd, 1, 5) > 0) {
      char buf[64];
      const ssize_t n = read(STDIN_FILENO, buf, sizeof buf);
      if (n <= 0) return 0;
      for (ssize_t i = 0; i < n; i++) device.onChar(buf[i], now_ms());
    }
    device.tick(now_ms());
  }
}
