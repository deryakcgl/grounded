// ADS1292R driver: 2-channel 24-bit biopotential front end with respiration measurement.
// Datasheet: TI SBAS502C (December 2011, revised April 2020). Section numbers refer to it.
//
// Hardware-free: every pin and SPI access goes through Ads1292rBus. On the STM32 the bus is the
// Arduino SPI library; on the Mac it is a simulated chip (test_native/fake_ads1292r.h) that
// checks the datasheet's rules, so the driver can be tested without hardware.
//
// Channel 1 = respiration (the demodulator works on channel 1, §8.6.1.10), channel 2 = ECG.
#pragma once
#include <stdint.h>

class Ads1292rBus {
 public:
  virtual void select(bool active) = 0;        // CS pin: active = low
  virtual uint8_t transfer(uint8_t out) = 0;   // one byte, SPI mode 1 (CPOL 0, CPHA 1), MSB first
  virtual void delayUs(uint32_t us) = 0;
  virtual void setReset(bool high) { (void)high; }   // PWDN/RESET pin, if it is wired
  virtual ~Ads1292rBus() {}
};

namespace ads {
// Opcodes (§8.5.2, Table 15)
enum : uint8_t {
  WAKEUP = 0x02, STANDBY = 0x04, RESET = 0x06, START = 0x08, STOP = 0x0A, OFFSETCAL = 0x1A,
  RDATAC = 0x10, SDATAC = 0x11, RDATA = 0x12, RREG = 0x20, WREG = 0x40
};
// Register addresses (§8.6, Table 16)
enum : uint8_t {
  ID, CONFIG1, CONFIG2, LOFF, CH1SET, CH2SET, RLD_SENS, LOFF_SENS, LOFF_STAT, RESP1, RESP2, GPIO,
  REG_COUNT
};
// Lead-off bits (LOFF_STAT[4:0], also in every data frame): 1 = electrode not connected
enum : uint8_t { IN1P_OFF = 1, IN1N_OFF = 2, IN2P_OFF = 4, IN2N_OFF = 8, RLD_OFF = 16 };

static const uint8_t ID_ADS1292R = 0x73;   // REV_ID[7:5]=011 (ADS1292R), bit4=1, [1:0]=11

// Timing. Internal clock fCLK = 512 kHz: tCLK = 1.95 us, tMOD = 4 tCLK = 7.8 us.
static const uint32_t T_POR_US = 40000;    // wait after power-up: 2^12 tMOD = 32 ms (§10.1)
static const uint32_t T_RESET_US = 100;    // RESET takes 9 tMOD = 70 us (§8.5.2.3)
static const uint32_t T_4CLK_US = 8;       // 4 tCLK = 7.8 us: between bytes of a command
                                           // (§8.5.2.10), after SDATAC, before CS high (§8.5.1.1)
static const uint8_t SETTLE_FRAMES = 4;    // first settled data: 4th DRDY after START (§8.5.1.10)

// ADC scale: full scale = +-VREF / gain = codes +-(2^23 - 1) (§8.3.8)
static const float VREF_V = 2.42f;         // internal reference, VREF_4V = 0
static const int32_t FULL_SCALE = 8388607;
}  // namespace ads

class Ads1292r {
 public:
  enum Error : uint8_t { OK, NO_DEVICE, WRONG_DEVICE, VERIFY_FAILED };

  struct Frame {
    int32_t resp;      // channel 1, raw ADC code
    int32_t ecg;       // channel 2, raw ADC code
    uint8_t lead_off;  // LOFF_STAT[4:0]; 0 = all electrodes connected
    bool valid;        // status word started with 1100 (otherwise: bus problem, discard)
  };

  // Register values written by begin(). Each bit is explained in ads1292r.cpp.
  struct Setting {
    uint8_t reg, value, mask;   // mask: bits that must read back as written
  };
  static const Setting CONFIG[];
  static const uint8_t CONFIG_COUNT;
  static const uint8_t ECG_GAIN = 6;     // must match CH2SET below

  explicit Ads1292r(Ads1292rBus& bus) : bus_(bus) {}

  // Reset, check the ID, write and verify the configuration, start continuous conversion.
  // power_up_wait: wait t_POR first (needed right after power is applied).
  Error begin(bool power_up_wait = true);

  // Read one frame. Call after DRDY falls (e.g. in the DRDY interrupt). 9 bytes over SPI.
  void readFrame(Frame& f);

  uint8_t id() const { return id_; }
  uint8_t failedRegister() const { return failed_reg_; }   // after VERIFY_FAILED

  // Low-level access (only while conversion is stopped / not in RDATAC)
  void command(uint8_t opcode);
  uint8_t readRegister(uint8_t reg);
  void writeRegister(uint8_t reg, uint8_t value);

  // Pure helpers (unit-tested on the Mac)
  static int32_t signExtend24(const uint8_t* p);
  static Frame parseFrame(const uint8_t raw[9]);
  static float ecgMillivoltsPerCode() { return ads::VREF_V * 1000.0f / ECG_GAIN / ads::FULL_SCALE; }

 private:
  Ads1292rBus& bus_;
  uint8_t id_ = 0;
  uint8_t failed_reg_ = 0;
};
