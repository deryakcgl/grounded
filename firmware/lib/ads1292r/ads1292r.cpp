#include "ads1292r.h"

const Ads1292r::Setting Ads1292r::CONFIG[] = {
    {ads::CONFIG1, 0x01, 0xFF},
    {ads::CONFIG2, 0xE0, 0xFF},
    {ads::LOFF, 0x10, 0xFF},
    {ads::CH1SET, 0x00, 0xFF},
    {ads::CH2SET, 0x00, 0xFF},
    {ads::RLD_SENS, 0x2C, 0xFF},
    {ads::LOFF_SENS, 0x0C, 0xFF},
    {ads::LOFF_STAT, 0x00, 0x40},
    {ads::RESP1, 0xEA, 0xFF},
    {ads::RESP2, 0x03, 0xFF},
};
const uint8_t Ads1292r::CONFIG_COUNT = sizeof(CONFIG) / sizeof(CONFIG[0]);

void Ads1292r::command(uint8_t opcode) {
  bus_.select(true);
  bus_.transfer(opcode);
  bus_.delayUs(ads::T_4CLK_US);
  bus_.select(false);
}

uint8_t Ads1292r::readRegister(uint8_t reg) {
  bus_.select(true);
  bus_.transfer(ads::RREG | reg);
  bus_.delayUs(ads::T_4CLK_US);
  bus_.transfer(0);
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

  bus_.setReset(false);
  bus_.delayUs(2 * ads::T_4CLK_US);
  bus_.setReset(true);
  bus_.delayUs(ads::T_RESET_US);
  command(ads::SDATAC);
  command(ads::RESET);
  bus_.delayUs(ads::T_RESET_US);
  command(ads::SDATAC);

  id_ = readRegister(ads::ID);
  if (id_ == 0x00 || id_ == 0xFF) return NO_DEVICE;
  if (id_ != ads::ID_ADS1292R) return WRONG_DEVICE;

  return apply(CONFIG, CONFIG_COUNT);
}

Ads1292r::Error Ads1292r::apply(const Setting* settings, uint8_t count) {
  command(ads::SDATAC);
  command(ads::STOP);
  for (uint8_t i = 0; i < count; i++) writeRegister(settings[i].reg, settings[i].value);
  for (uint8_t i = 0; i < count; i++) {
    const Setting& s = settings[i];
    if ((readRegister(s.reg) & s.mask) != (s.value & s.mask)) {
      failed_reg_ = s.reg;
      return VERIFY_FAILED;
    }
  }
  command(ads::RDATAC);
  command(ads::START);
  return OK;
}

void Ads1292r::readRegisters(uint8_t out[ads::REG_COUNT]) {
  command(ads::SDATAC);
  command(ads::STOP);
  for (uint8_t r = 0; r < ads::REG_COUNT; r++) out[r] = readRegister(r);
}

Ads1292r::Error Ads1292r::startTestSignal() {
  static const Setting TEST[] = {
      {ads::CONFIG2, 0xE3, 0xFF},
      {ads::CH1SET, 0x05, 0xFF},
      {ads::CH2SET, 0x05, 0xFF},
  };
  return apply(TEST, sizeof TEST / sizeof TEST[0]);
}

Ads1292r::Error Ads1292r::startNormal() { return apply(CONFIG, CONFIG_COUNT); }

void Ads1292r::readFrame(Frame& f) {
  uint8_t raw[9];
  bus_.select(true);
  for (uint8_t i = 0; i < 9; i++) raw[i] = bus_.transfer(0);
  bus_.delayUs(ads::T_4CLK_US);
  bus_.select(false);
  f = parseFrame(raw);
}

int32_t Ads1292r::signExtend24(const uint8_t* p) {
  int32_t v = ((int32_t)p[0] << 16) | ((int32_t)p[1] << 8) | p[2];
  if (v & 0x800000) v -= 0x1000000;
  return v;
}

Ads1292r::Frame Ads1292r::parseFrame(const uint8_t raw[9]) {
  const uint32_t status = ((uint32_t)raw[0] << 16) | ((uint32_t)raw[1] << 8) | raw[2];
  Frame f;
  f.valid = (status >> 20) == 0xC;
  f.lead_off = (uint8_t)((status >> 15) & 0x1F);
  f.resp = signExtend24(raw + 3);
  f.ecg = signExtend24(raw + 6);
  return f;
}
