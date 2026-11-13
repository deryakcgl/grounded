#pragma once
#include <stdint.h>

#include <atomic>

template <typename T, uint16_t N>
class SpscFifo {
  static_assert(N >= 2 && N <= 32768 && (N & (N - 1)) == 0, "N must be a power of two");

 public:
  bool push(const T& item) {
    const uint16_t head = head_.load(std::memory_order_relaxed);
    if ((uint16_t)(head - tail_.load(std::memory_order_acquire)) == N) {
      dropped_++;
      return false;
    }
    buf_[head & (N - 1)] = item;
    head_.store((uint16_t)(head + 1), std::memory_order_release);
    return true;
  }

  bool pop(T& item) {
    const uint16_t tail = tail_.load(std::memory_order_relaxed);
    if (tail == head_.load(std::memory_order_acquire)) return false;
    item = buf_[tail & (N - 1)];
    tail_.store((uint16_t)(tail + 1), std::memory_order_release);
    return true;
  }

  uint16_t size() const {
    return (uint16_t)(head_.load(std::memory_order_acquire) - tail_.load(std::memory_order_acquire));
  }
  uint32_t dropped() const { return dropped_; }

 private:
  T buf_[N];
  std::atomic<uint16_t> head_{0};
  std::atomic<uint16_t> tail_{0};
  volatile uint32_t dropped_ = 0;
};
