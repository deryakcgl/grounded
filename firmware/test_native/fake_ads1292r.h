// Simulated ADS1292R for testing the driver on the Mac (test only, not firmware).
// It plays the chip's side of the SPI bus and records every datasheet rule the driver breaks
// (SBAS502C section numbers in the messages). A real chip would just misbehave silently.
#pragma once
#include <stdint.h>
#include <stdio.h>

#include <string>
#include <vector>

#include "ads1292r.h"

class FakeAds1292r : public Ads1292rBus {
 public:
  // Register reset values (Table 16)
  static constexpr uint8_t RESET_VALUES[ads::REG_COUNT] = {0x73, 0x02, 0x80, 0x10, 0x00, 0x00,
                                                           0x00, 0x00, 0x00, 0x00, 0x02, 0x0C};
  uint8_t regs[ads::REG_COUNT];
  uint8_t id = ads::ID_ADS1292R;    // change to simulate another part
  uint8_t stuck_low = 0;            // bits that always read 0 (simulates a broken MISO line)
  bool rdatac = true;               // the chip powers up in RDATAC mode (§8.5.2.7)
  bool converting = false;
  std::vector<std::string> violations;

  FakeAds1292r() { resetRegisters(); }

  // --- The "analog" side: a conversion finished, DRDY falls ---
  void convert(int32_t ch1, int32_t ch2, uint8_t lead_off = 0) {
    const uint32_t status = 0xC00000u | ((uint32_t)(lead_off & 0x1F) << 15);
    put24(frame_, status);
    put24(frame_ + 3, (uint32_t)ch1 & 0xFFFFFF);
    put24(frame_ + 6, (uint32_t)ch2 & 0xFFFFFF);
    frame_pos_ = 0;
    if (converting) frames_ready_++;
  }
  int frames_ready_ = 0;

  // --- Ads1292rBus: the chip's side of SPI ---
  void select(bool active) override {
    if (active) {
      cs_ = true;
      state_ = OPCODE;
      frame_pos_ = 0;
    } else {
      if (cs_ && since_byte_us_ < ads::T_4CLK_US) violate("CS raised < 4 tCLK after last SCLK (8.5.1.1)");
      cs_ = false;
    }
  }

  uint8_t transfer(uint8_t in) override {
    if (!cs_) violate("SPI transfer with CS high (8.5.1.1)");
    if (state_ != OPCODE && state_ != DATA_READ && since_byte_us_ < ads::T_4CLK_US) {
      violate("< 4 tCLK between bytes of a multi-byte command (8.5.2.10)");
    }
    if (busy_us_ > 0 && state_ == OPCODE) violate("command sent while the previous one was executing");
    const uint8_t out = step(in);
    since_byte_us_ = 0;
    return out;
  }

  void delayUs(uint32_t us) override {
    since_byte_us_ += us;
    busy_us_ = busy_us_ > us ? busy_us_ - us : 0;
  }

  void setReset(bool high) override {
    if (!high) {
      reset_low_ = true;
    } else if (reset_low_) {
      reset_low_ = false;
      chipReset();
    }
  }

 private:
  enum State { OPCODE, RREG_COUNT, RREG_DATA, WREG_COUNT, WREG_DATA, DATA_READ, IGNORE };

  static void put24(uint8_t* p, uint32_t v) {
    p[0] = (uint8_t)(v >> 16);
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)v;
  }

  void violate(const std::string& what) { violations.push_back(what); }

  void resetRegisters() {
    for (int i = 0; i < ads::REG_COUNT; i++) regs[i] = RESET_VALUES[i];
    regs[ads::ID] = id;
  }

  void chipReset() {
    resetRegisters();
    rdatac = true;
    converting = false;
    busy_us_ = 70;   // RESET takes 9 tMOD (8.5.2.3)
  }

  void checkMustBits(uint8_t reg, uint8_t v) {
    struct Rule { uint8_t reg, mask, value; const char* name; };
    static const Rule rules[] = {
        {ads::CONFIG1, 0x78, 0x00, "CONFIG1[6:3] must be 0"},
        {ads::CONFIG2, 0x84, 0x80, "CONFIG2[7] must be 1, [2] must be 0"},
        {ads::LOFF, 0x12, 0x10, "LOFF[4] must be 1, [1] must be 0"},
        {ads::LOFF_SENS, 0xC0, 0x00, "LOFF_SENS[7:6] must be 0"},
        {ads::LOFF_STAT, 0xA0, 0x00, "LOFF_STAT[7], [5] must be 0"},
        {ads::RESP1, 0x02, 0x02, "RESP1[1] must be 1"},
        {ads::RESP2, 0x79, 0x01, "RESP2[6:3] must be 0, [0] must be 1"},
        {ads::GPIO, 0xF0, 0x00, "GPIO[7:4] must be 0"},
    };
    for (const Rule& r : rules) {
      if (r.reg == reg && (v & r.mask) != r.value) violate(std::string(r.name) + " (8.6.1)");
    }
  }

  uint8_t step(uint8_t in) {
    switch (state_) {
      case OPCODE:
        if (rdatac && in == 0x00) {          // clocking out data in RDATAC mode
          state_ = DATA_READ;
          if (frames_ready_ == 0) violate("data read without a new DRDY");
          frames_ready_ = 0;
          return frame_[frame_pos_++];
        }
        if (rdatac && in != ads::SDATAC && in != ads::START && in != ads::STOP &&
            in != ads::WAKEUP && in != ads::STANDBY) {
          char m[80];
          snprintf(m, sizeof m, "opcode 0x%02X in RDATAC mode: SDATAC first (8.5.2.7)", in);
          violate(m);
          state_ = IGNORE;
          return 0;
        }
        if ((in & 0xE0) == ads::RREG) { addr_ = in & 0x1F; state_ = RREG_COUNT; return 0; }
        if ((in & 0xE0) == ads::WREG) { addr_ = in & 0x1F; state_ = WREG_COUNT; return 0; }
        switch (in) {
          case ads::SDATAC: rdatac = false; break;
          case ads::RDATAC: rdatac = true; break;
          case ads::START: converting = true; break;
          case ads::STOP: converting = false; break;
          case ads::RESET: chipReset(); break;
          case ads::WAKEUP: case ads::STANDBY: case ads::OFFSETCAL: case ads::RDATA: break;
          default: {
            char m[48];
            snprintf(m, sizeof m, "unknown opcode 0x%02X", in);
            violate(m);
          }
        }
        state_ = IGNORE;
        return 0;
      case RREG_COUNT:
      case WREG_COUNT:
        count_ = (in & 0x1F) + 1;
        state_ = state_ == RREG_COUNT ? RREG_DATA : WREG_DATA;
        return 0;
      case RREG_DATA: {
        const uint8_t v = addr_ < ads::REG_COUNT ? regs[addr_] : 0;
        addr_++;
        if (--count_ == 0) state_ = IGNORE;
        return v & (uint8_t)~stuck_low;
      }
      case WREG_DATA:
        if (addr_ == ads::ID) {
          violate("write to read-only ID register");
        } else if (addr_ < ads::REG_COUNT) {
          checkMustBits(addr_, in);
          // LOFF_STAT[4:0] are read-only status bits
          regs[addr_] = addr_ == ads::LOFF_STAT ? (uint8_t)((in & 0xE0) | (regs[addr_] & 0x1F)) : in;
        }
        addr_++;
        if (--count_ == 0) state_ = IGNORE;
        return 0;
      case DATA_READ:
        // Multiple readback: after the last byte the frame repeats (8.5.1.5)
        if (frame_pos_ >= 9) frame_pos_ = 0;
        return frame_[frame_pos_++];
      case IGNORE:
        return 0;
    }
    return 0;
  }

  bool cs_ = false;
  bool reset_low_ = false;
  State state_ = OPCODE;
  uint8_t addr_ = 0, count_ = 0;
  uint8_t frame_[9] = {};
  int frame_pos_ = 0;
  uint32_t since_byte_us_ = 1000000;
  uint32_t busy_us_ = 0;
};
