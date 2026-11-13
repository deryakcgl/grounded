#include "ads1292r.h"

// Configuration for Grounded. Bit fields from §8.6.1 (Tables 17-28).
// "tune" = a reasonable starting value that must be checked on the real hardware.
const Ads1292r::Setting Ads1292r::CONFIG[] = {
    // CONFIG1 0000 0001: continuous conversion; DR = 001 -> 250 SPS (ECG rate; respiration is
    // averaged down to 25 Hz in firmware)
    {ads::CONFIG1, 0x01, 0xFF},
    // CONFIG2 1110 0000: bit7 must be 1; PDB_LOFF_COMP = 1 (lead-off comparators on);
    // PDB_REFBUF = 1 (internal reference ON - the default is OFF = external reference!);
    // VREF_4V = 0 (2.42 V); CLK_EN = 0; INT_TEST = 0 (no test signal)
    {ads::CONFIG2, 0xE0, 0xFF},
    // LOFF 0001 0000: comparator thresholds 95% / 5%; bit4 must be 1; 6 nA lead-off current;
    // DC lead-off detection
    {ads::LOFF, 0x10, 0xFF},
    // CH1SET 0000 0000: channel 1 (respiration) on, gain 6 (tune), normal electrode input
    {ads::CH1SET, 0x00, 0xFF},
    // CH2SET 0000 0000: channel 2 (ECG) on, gain 6, normal electrode input. Gain 6 keeps
    // +-400 mV of range: dry/textile electrodes can have large DC offsets.
    {ads::CH2SET, 0x00, 0xFF},
    // RLD_SENS 0010 1100: PDB_RLD = 1 (right-leg drive on, reduces mains hum); derived from
    // channel 2 (ECG) inputs: RLD2N = RLD2P = 1
    {ads::RLD_SENS, 0x2C, 0xFF},
    // LOFF_SENS 0000 1100: lead-off detection on the ECG electrodes (LOFF2N, LOFF2P).
    // Not on channel 1: it carries the respiration excitation current.
    {ads::LOFF_SENS, 0x0C, 0xFF},
    // LOFF_STAT 0000 0000: CLK_DIV = 0 (internal 512 kHz clock). Bits 4:0 are read-only status,
    // so only CLK_DIV is checked.
    {ads::LOFF_STAT, 0x00, 0x40},
    // RESP1 1110 1010: demodulation and modulation on; RESP_PH = 1010 (112.5 deg at 32 kHz, tune:
    // the best phase depends on electrodes and cables); bit1 must be 1; RESP_CTRL = 0 (internal clock)
    {ads::RESP1, 0xEA, 0xFF},
    // RESP2 0000 0011: CALIB_ON = 0; RESP_FREQ = 0 (32 kHz); RLDREF_INT = 1 (internal
    // mid-supply reference); bit0 must be 1
    {ads::RESP2, 0x03, 0xFF},
};
const uint8_t Ads1292r::CONFIG_COUNT = sizeof(CONFIG) / sizeof(CONFIG[0]);

void Ads1292r::command(uint8_t opcode) {
  bus_.select(true);
  bus_.transfer(opcode);
  bus_.delayUs(ads::T_4CLK_US);   // decode time, and the minimum before CS goes high
  bus_.select(false);
}

uint8_t Ads1292r::readRegister(uint8_t reg) {
  bus_.select(true);
  bus_.transfer(ads::RREG | reg);
  bus_.delayUs(ads::T_4CLK_US);   // multi-byte command: 4 tCLK between bytes
  bus_.transfer(0);               // count - 1 = 0: one register
  bus_.delayUs(ads::T_4CLK_US);
  const uint8_t v = bus_.transfer(0);
  bus_.delayUs(ads::T_4CLK_US);
  bus_.select(false);
  return v;
}

void Ads1292r::writeRegister(uint8_t reg, uint8_t value) {
  bus_.select(true);
  bus_.transfer(ads::WREG | reg);
  bus_.delayUs(ads::T_4CLK_US);
  bus_.transfer(0);
  bus_.delayUs(ads::T_4CLK_US);
  bus_.transfer(value);
  bus_.delayUs(ads::T_4CLK_US);
  bus_.select(false);
}

Ads1292r::Error Ads1292r::begin(bool power_up_wait) {
  if (power_up_wait) bus_.delayUs(ads::T_POR_US);

  // Reset pulse on the pin (if wired; >= 1 tMOD low), then the RESET command as well, so it
  // works without the pin. The chip starts in RDATAC mode, where it only listens for SDATAC,
  // so SDATAC comes first - and again after the reset, which brings RDATAC back.
  bus_.setReset(false);
  bus_.delayUs(2 * ads::T_4CLK_US);
  bus_.setReset(true);
  bus_.delayUs(ads::T_RESET_US);
  command(ads::SDATAC);
  command(ads::RESET);
  bus_.delayUs(ads::T_RESET_US);
  command(ads::SDATAC);

  id_ = readRegister(ads::ID);
  if (id_ == 0x00 || id_ == 0xFF) return NO_DEVICE;   // MISO stuck low/high: nothing answers
  if (id_ != ads::ID_ADS1292R) return WRONG_DEVICE;   // e.g. ADS1292 (0x53): no respiration

  for (uint8_t i = 0; i < CONFIG_COUNT; i++) writeRegister(CONFIG[i].reg, CONFIG[i].value);
  // Read everything back: catches wiring faults and a chip that silently ignored a write
  for (uint8_t i = 0; i < CONFIG_COUNT; i++) {
    const Setting& s = CONFIG[i];
    if ((readRegister(s.reg) & s.mask) != (s.value & s.mask)) {
      failed_reg_ = s.reg;
      return VERIFY_FAILED;
    }
  }

  command(ads::RDATAC);   // before START: no DRDY yet, so no RDATAC keep-out zone (§8.5.2.7)
  command(ads::START);    // START pin tied low; conversions are started by command (§8.5.1.9)
  return OK;
}

void Ads1292r::readFrame(Frame& f) {
  uint8_t raw[9];
  bus_.select(true);
  for (uint8_t i = 0; i < 9; i++) raw[i] = bus_.transfer(0);   // DIN low while reading (§8.5.1.5)
  bus_.delayUs(ads::T_4CLK_US);
  bus_.select(false);
  f = parseFrame(raw);
}

int32_t Ads1292r::signExtend24(const uint8_t* p) {
  int32_t v = ((int32_t)p[0] << 16) | ((int32_t)p[1] << 8) | p[2];
  if (v & 0x800000) v -= 0x1000000;   // bit 23 is the sign of a 24-bit two's complement number
  return v;
}

Ads1292r::Frame Ads1292r::parseFrame(const uint8_t raw[9]) {
  // Status word: 1100 + LOFF_STAT[4:0] + GPIO[1:0] + 13 zeros (§8.5.1.5)
  const uint32_t status = ((uint32_t)raw[0] << 16) | ((uint32_t)raw[1] << 8) | raw[2];
  Frame f;
  f.valid = (status >> 20) == 0xC;
  f.lead_off = (uint8_t)((status >> 15) & 0x1F);
  f.resp = signExtend24(raw + 3);
  f.ecg = signExtend24(raw + 6);
  return f;
}
