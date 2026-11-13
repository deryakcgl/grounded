#include "wokwi-api.h"

#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define PI 3.14159265358979

enum { WAKEUP = 0x02, STANDBY = 0x04, RESET = 0x06, START = 0x08, STOP = 0x0A, OFFSETCAL = 0x1A,
       RDATAC = 0x10, SDATAC = 0x11, RDATA = 0x12 };
enum { R_ID, R_CONFIG1, R_CONFIG2, R_LOFF, R_CH1SET, R_CH2SET, R_RLD_SENS, R_LOFF_SENS,
       R_LOFF_STAT, R_RESP1, R_RESP2, R_GPIO, R_COUNT };
static const uint8_t RESET_VALUES[R_COUNT] = {0x73, 0x02, 0x80, 0x10, 0x00, 0x00,
                                              0x00, 0x00, 0x00, 0x00, 0x02, 0x0C};
static const int GAINS[8] = {6, 1, 2, 3, 4, 8, 12, 6};

#define T_4CLK_NS 7812
#define FULL_SCALE 8388607

typedef enum { ST_OPCODE, ST_RREG_COUNT, ST_RREG_DATA, ST_WREG_COUNT, ST_WREG_DATA, ST_DATA,
               ST_IGNORE } spi_state_t;

typedef struct {
  pin_t cs, drdy, pwdn, start;
  spi_dev_t spi;
  uint8_t buf[1];
  timer_t conv_timer, drdy_timer;
  uint32_t a_heart, a_breath, a_hrv, a_hold, a_contact;

  uint8_t regs[R_COUNT];
  bool rdatac, converting, drdy_low, pwdn_low;
  spi_state_t state;
  uint8_t addr, count, frame[9], frame_pos;
  uint64_t last_byte_ns;
  uint32_t frames_since_start, violations;

  double beat_t, rr;
  double breath_phase;
  double resp_hold;
  double test_t;
  uint32_t rng;
} chip_t;

static void violate(chip_t* c, const char* what) {
  if (c->violations++ < 20) printf("ADS1292R: datasheet rule broken: %s\n", what);
}

static double noise(chip_t* c) {
  c->rng = c->rng * 1664525u + 1013904223u;
  return (double)(c->rng >> 8) / 8388608.0 - 1.0;
}

static double gauss(double t, double center, double width) {
  const double x = (t - center) / width;
  return exp(-0.5 * x * x);
}

static double pqrst(double t) {
  const double r = 0.25;
  return 0.12 * gauss(t, r - 0.20, 0.025)
       - 0.12 * gauss(t, r - 0.03, 0.008)
       + 1.20 * gauss(t, r, 0.010)
       - 0.25 * gauss(t, r + 0.03, 0.010)
       + 0.30 * gauss(t, r + 0.25, 0.040);
}

static void next_sample(chip_t* c, double dt, int32_t* resp_code, int32_t* ecg_code, uint8_t* loff) {
  const double heart = attr_read(c->a_heart), breath = attr_read(c->a_breath);
  const double swing = attr_read(c->a_hrv) / 1000.0;
  const bool hold = attr_read(c->a_hold) != 0, contact = attr_read(c->a_contact) != 0;

  if (!hold) {
    c->breath_phase += dt * breath / 60.0;
    if (c->breath_phase >= 1.0) c->breath_phase -= 1.0;
  }
  double resp = hold ? c->resp_hold : sin(2.0 * PI * c->breath_phase);
  if (!hold) c->resp_hold = resp;
  resp += 0.01 * noise(c);

  c->beat_t += dt;
  if (c->beat_t >= c->rr) {
    c->beat_t -= c->rr;
    c->rr = 60.0 / heart - swing * sin(2.0 * PI * c->breath_phase) + 0.004 * noise(c);
    if (c->rr < 0.25) c->rr = 0.25;
  }
  double ecg_mv = pqrst(c->beat_t) + 0.05 * sin(2.0 * PI * c->breath_phase) + 0.01 * noise(c);

  *loff = 0;
  if (!contact) {
    if (c->regs[R_CONFIG2] & 0x40) *loff = c->regs[R_LOFF_SENS] & 0x0F;
    ecg_mv = 1e6;
  }
  c->regs[R_LOFF_STAT] = (uint8_t)((c->regs[R_LOFF_STAT] & 0xE0) | *loff);

  const int g_ecg = GAINS[(c->regs[R_CH2SET] >> 4) & 7], g_resp = GAINS[(c->regs[R_CH1SET] >> 4) & 7];
  const double vref_mv = (c->regs[R_CONFIG2] & 0x10) ? 4033.0 : 2420.0;
  double e = ecg_mv * g_ecg / vref_mv * FULL_SCALE;
  double r = (c->regs[R_RESP1] & 0xC0) == 0xC0 ? resp * 200000.0 * g_resp : 2000.0 * noise(c);
  if (!(c->regs[R_CONFIG2] & 0x20)) {
    e = FULL_SCALE * noise(c);
    r = FULL_SCALE * noise(c);
  }
  if (e > FULL_SCALE) e = FULL_SCALE;
  if (e < -FULL_SCALE - 1) e = -FULL_SCALE - 1;
  c->test_t += dt;
  const double test_amp = (double)FULL_SCALE / 2400.0;
  const bool high = !(c->regs[R_CONFIG2] & 0x01) || fmod(c->test_t, 1.0) < 0.5;
  const double test = (c->regs[R_CONFIG2] & 0x02) ? (high ? test_amp : -test_amp) : 0.0;
  const uint8_t mux1 = c->regs[R_CH1SET] & 0x0F, mux2 = c->regs[R_CH2SET] & 0x0F;
  if (mux1 == 0x5) r = test * g_resp;
  if (mux2 == 0x5) e = test * g_ecg;
  if (mux1 == 0x1) r = 20.0 * noise(c);
  if (mux2 == 0x1) e = 20.0 * noise(c);

  *ecg_code = (int32_t)e;
  *resp_code = (int32_t)r;
}

static void put24(uint8_t* p, uint32_t v) {
  p[0] = (uint8_t)(v >> 16);
  p[1] = (uint8_t)(v >> 8);
  p[2] = (uint8_t)v;
}

static uint32_t data_rate(chip_t* c) { return 125u << (c->regs[R_CONFIG1] & 7); }

static void on_conversion(void* user_data) {
  chip_t* c = user_data;
  int32_t resp = 0, ecg = 0;
  uint8_t loff = 0;
  next_sample(c, 1.0 / data_rate(c), &resp, &ecg, &loff);
  if (c->frames_since_start++ < 3) resp = ecg = 0;

  put24(c->frame, 0xC00000u | ((uint32_t)loff << 15) | ((uint32_t)(c->regs[R_GPIO] & 3) << 13));
  put24(c->frame + 3, (uint32_t)resp & 0xFFFFFF);
  put24(c->frame + 6, (uint32_t)ecg & 0xFFFFFF);

  if (c->drdy_low) {
    pin_write(c->drdy, HIGH);
    timer_start(c->drdy_timer, 8, false);
  } else {
    pin_write(c->drdy, LOW);
    c->drdy_low = true;
  }
}

static void on_drdy_timer(void* user_data) {
  chip_t* c = user_data;
  pin_write(c->drdy, LOW);
  c->drdy_low = true;
}

static void start_conversions(chip_t* c) {
  if (c->converting) return;
  c->converting = true;
  c->frames_since_start = 0;
  timer_start(c->conv_timer, 1000000u / data_rate(c), true);
  printf("ADS1292R: converting at %u SPS | ECG gain %d | respiration %s | reference %s | lead-off %s\n",
         (unsigned)data_rate(c), GAINS[(c->regs[R_CH2SET] >> 4) & 7],
         (c->regs[R_RESP1] & 0xC0) == 0xC0 ? "on" : "OFF",
         (c->regs[R_CONFIG2] & 0x20) ? "internal" : "OFF (CONFIG2 bit5 = 0: data is garbage!)",
         (c->regs[R_CONFIG2] & 0x40) ? "on" : "off");
}

static void stop_conversions(chip_t* c) {
  c->converting = false;
  timer_stop(c->conv_timer);
}

static void chip_reset(chip_t* c) {
  for (int i = 0; i < R_COUNT; i++) c->regs[i] = RESET_VALUES[i];
  c->rdatac = true;
  stop_conversions(c);
  pin_write(c->drdy, HIGH);
  c->drdy_low = false;
}

static void check_gap(chip_t* c, uint64_t now) {
  if (now - c->last_byte_ns < T_4CLK_NS) violate(c, "< 4 tCLK between bytes of a multi-byte command (8.5.2.10)");
}

static void check_must_bits(chip_t* c, uint8_t reg, uint8_t v) {
  static const struct { uint8_t reg, mask, value; const char* text; } rules[] = {
      {R_CONFIG1, 0x78, 0x00, "CONFIG1[6:3] must be 0"},
      {R_CONFIG2, 0x84, 0x80, "CONFIG2[7] must be 1, [2] must be 0"},
      {R_LOFF, 0x12, 0x10, "LOFF[4] must be 1, [1] must be 0"},
      {R_LOFF_SENS, 0xC0, 0x00, "LOFF_SENS[7:6] must be 0"},
      {R_RESP1, 0x02, 0x02, "RESP1[1] must be 1"},
      {R_RESP2, 0x79, 0x01, "RESP2[6:3] must be 0, [0] must be 1"},
  };
  for (unsigned i = 0; i < sizeof rules / sizeof rules[0]; i++) {
    if (rules[i].reg == reg && (v & rules[i].mask) != rules[i].value) violate(c, rules[i].text);
  }
}

static uint8_t handle_byte(chip_t* c, uint8_t in, uint64_t now) {
  switch (c->state) {
    case ST_OPCODE:
      if (c->rdatac && in == 0x00) {
        c->state = ST_DATA;
        if (c->drdy_low) {
          pin_write(c->drdy, HIGH);
          c->drdy_low = false;
        }
        c->frame_pos = 2;
        return c->frame[1];
      }
      if (c->rdatac && in != SDATAC && in != START && in != STOP && in != WAKEUP && in != STANDBY) {
        violate(c, "command in RDATAC mode: send SDATAC first (8.5.2.7)");
        c->state = ST_IGNORE;
        return 0;
      }
      if ((in & 0xE0) == 0x20) { c->addr = in & 0x1F; c->state = ST_RREG_COUNT; return 0; }
      if ((in & 0xE0) == 0x40) { c->addr = in & 0x1F; c->state = ST_WREG_COUNT; return 0; }
      switch (in) {
        case SDATAC: c->rdatac = false; break;
        case RDATAC: c->rdatac = true; break;
        case START: start_conversions(c); break;
        case STOP: stop_conversions(c); break;
        case RESET: chip_reset(c); break;
        default: break;
      }
      c->state = ST_IGNORE;
      return 0;

    case ST_RREG_COUNT:
      check_gap(c, now);
      c->count = (uint8_t)((in & 0x1F) + 1);
      c->state = ST_RREG_DATA;
      return c->addr < R_COUNT ? c->regs[c->addr] : 0;

    case ST_RREG_DATA:
      check_gap(c, now);
      c->addr++;
      if (--c->count == 0) { c->state = ST_IGNORE; return 0; }
      return c->addr < R_COUNT ? c->regs[c->addr] : 0;

    case ST_WREG_COUNT:
      check_gap(c, now);
      c->count = (uint8_t)((in & 0x1F) + 1);
      c->state = ST_WREG_DATA;
      return 0;

    case ST_WREG_DATA:
      check_gap(c, now);
      if (c->addr == R_ID) {
        violate(c, "write to the read-only ID register");
      } else if (c->addr < R_COUNT) {
        check_must_bits(c, c->addr, in);
        c->regs[c->addr] = c->addr == R_LOFF_STAT ? (uint8_t)((in & 0xE0) | (c->regs[c->addr] & 0x1F)) : in;
      }
      c->addr++;
      if (--c->count == 0) c->state = ST_IGNORE;
      return 0;

    case ST_DATA:
      return c->frame[c->frame_pos++ % 9];

    case ST_IGNORE:
    default:
      return 0;
  }
}

static void on_spi_done(void* user_data, uint8_t* buffer, uint32_t count) {
  chip_t* c = user_data;
  if (count == 0) return;
  const uint64_t now = get_sim_nanos();
  buffer[0] = handle_byte(c, buffer[0], now);
  c->last_byte_ns = now;
  if (pin_read(c->cs) == LOW) spi_start(c->spi, c->buf, 1);
}

static void on_pin_change(void* user_data, pin_t pin, uint32_t value) {
  chip_t* c = user_data;
  if (pin == c->cs) {
    if (value == LOW) {
      c->state = ST_OPCODE;
      c->buf[0] = c->rdatac ? c->frame[0] : 0;
      spi_start(c->spi, c->buf, 1);
    } else {
      spi_stop(c->spi);
    }
  } else if (pin == c->pwdn) {
    if (value == LOW) c->pwdn_low = true;
    else if (c->pwdn_low) { c->pwdn_low = false; chip_reset(c); }
  } else if (pin == c->start) {
    if (value == HIGH) start_conversions(c);
    else stop_conversions(c);
  }
}

void chip_init(void) {
  chip_t* c = calloc(1, sizeof(chip_t));
  c->rng = 12345;
  c->rr = 60.0 / 70.0;

  c->cs = pin_init("CS", INPUT_PULLUP);
  c->drdy = pin_init("DRDY", OUTPUT_HIGH);
  c->pwdn = pin_init("PWDN", INPUT_PULLUP);
  c->start = pin_init("START", INPUT_PULLDOWN);

  c->a_heart = attr_init("heartRate", 70);
  c->a_breath = attr_init("breathRate", 15);
  c->a_hrv = attr_init("hrvDepth", 40);
  c->a_hold = attr_init("holdBreath", 0);
  c->a_contact = attr_init("electrodeContact", 1);

  pin_watch_config_t watch = {.edge = BOTH, .pin_change = on_pin_change, .user_data = c};
  pin_watch(c->cs, &watch);
  pin_watch(c->pwdn, &watch);
  pin_watch(c->start, &watch);

  spi_config_t spi = {
      .sck = pin_init("SCLK", INPUT),
      .mosi = pin_init("DIN", INPUT),
      .miso = pin_init("DOUT", INPUT),
      .mode = 1,
      .done = on_spi_done,
      .user_data = c,
  };
  c->spi = spi_init(&spi);

  timer_config_t conv = {.callback = on_conversion, .user_data = c};
  c->conv_timer = timer_init(&conv);
  timer_config_t drdy = {.callback = on_drdy_timer, .user_data = c};
  c->drdy_timer = timer_init(&drdy);

  chip_reset(c);
  printf("ADS1292R simulator ready (ID 0x73)\n");
}
