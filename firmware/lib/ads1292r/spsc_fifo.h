// Single-producer single-consumer FIFO: the DRDY interrupt pushes frames, loop() pops them.
// Lets the main loop fall behind for a while (a slow beat search, a Bluetooth burst) without
// losing samples: only the AVERAGE processing time has to fit the sample period.
//
// Lock-free and safe with exactly one writer (the interrupt) and one reader (the main loop):
//   - only the writer changes head_, only the reader changes tail_
//   - head_/tail_ are free-running counters; slot = counter & (N - 1). N is a power of two,
//     so this is a bit mask, not a '%' (no hardware divide on the Cortex-M0+), and
//     head_ - tail_ is the fill level even after the counters wrap around.
//   - std::atomic with release/acquire: the frame is fully written BEFORE the new head_ is
//     visible to the reader. Without it, the compiler may reorder those two stores.
#pragma once
#include <stdint.h>

#include <atomic>

template <typename T, uint16_t N>
class SpscFifo {
  static_assert(N >= 2 && N <= 32768 && (N & (N - 1)) == 0, "N must be a power of two");

 public:
  // Interrupt side. Returns false (and counts a drop) if the FIFO is full.
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

  // Main-loop side. Returns false if empty.
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
  uint32_t dropped() const { return dropped_; }   // written by the interrupt only

 private:
  T buf_[N];
  std::atomic<uint16_t> head_{0};
  std::atomic<uint16_t> tail_{0};
  volatile uint32_t dropped_ = 0;
};
