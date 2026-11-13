#pragma once
#include <stdint.h>

class Ads1292rBus {
 public:
  virtual void select(bool active) = 0;
  virtual uint8_t transfer(uint8_t out) = 0;
  virtual void delayUs(uint32_t us) = 0;
  virtual void setReset(bool high) { (void)high; }
  virtual ~Ads1292rBus() {}
};

namespace ads {
enum : uint8_t {
  WAKEUP = 0x02, STANDBY = 0x04, RESET = 0x06, START = 0x08, STOP = 0x0A, OFFSETCAL = 0x1A,
  RDATAC = 0x10, SDATAC = 0x11, RDATA = 0x12, RREG = 0x20, WREG = 0x40
};
enum : uint8_t {
  ID, CONFIG1, CONFIG2, LOFF, CH1SET, CH2SET, RLD_SENS, LOFF_SENS, LOFF_STAT, RESP1, RESP2, GPIO,
  REG_COUNT
};
enum : uint8_t { IN1P_OFF = 1, IN1N_OFF = 2, IN2P_OFF = 4, IN2N_OFF = 8, RLD_OFF = 16 };

static const uint8_t ID_ADS1292R = 0x73;

static const uint32_t T_POR_US = 40000;
static const uint32_t T_RESET_US = 100;
static const uint32_t T_4CLK_US = 8;
static const uint8_t SETTLE_FRAMES = 4;

static const float VREF_V = 2.42f;
static const int32_t FULL_SCALE = 8388607;
}

class Ads1292r {
 public:
  enum Error : uint8_t { OK, NO_DEVICE, WRONG_DEVICE, VERIFY_FAILED };

  struct Frame {
    int32_t resp;
    int32_t ecg;
    uint8_t lead_off;
    bool valid;
  };

  struct Setting {
    uint8_t reg, value, mask;
  };
  static const Setting CONFIG[];
  static const uint8_t CONFIG_COUNT;
  static const uint8_t ECG_GAIN = 6;

  explicit Ads1292r(Ads1292rBus& bus) : bus_(bus) {}

  Error begin(bool power_up_wait = true);

  void readFrame(Frame& f);

  void readRegisters(uint8_t out[ads::REG_COUNT]);
  Error startTestSignal();
  Error startNormal();
  static int32_t testSignalCodes(uint8_t gain) { return (int32_t)((int64_t)ads::FULL_SCALE * gain / 2400); }
  static bool testSignalOk(int32_t peak_to_peak, uint8_t gain) {
    const int32_t expected = 2 * testSignalCodes(gain);
    return peak_to_peak > expected * 85 / 100 && peak_to_peak < expected * 115 / 100;
  }

  uint8_t id() const { return id_; }
  uint8_t failedRegister() const { return failed_reg_; }

  void command(uint8_t opcode);
  uint8_t readRegister(uint8_t reg);
  void writeRegister(uint8_t reg, uint8_t value);

  static int32_t signExtend24(const uint8_t* p);
  static Frame parseFrame(const uint8_t raw[9]);
  static float ecgMillivoltsPerCode() { return ads::VREF_V * 1000.0f / ECG_GAIN / ads::FULL_SCALE; }

 private:
  Error apply(const Setting* settings, uint8_t count);

  Ads1292rBus& bus_;
  uint8_t id_ = 0;
  uint8_t failed_reg_ = 0;
};
