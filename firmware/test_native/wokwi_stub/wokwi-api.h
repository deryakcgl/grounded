/* Minimal stand-in for the Wokwi Chips API (signatures from docs.wokwi.com/chips-api), so the
 * ADS1292R custom chip (grounded_pod/wokwi/ads1292r.chip.c) can run on the Mac.
 * The functions are implemented by test_native/wokwi_chip_sim.cpp. Test only. */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef int32_t pin_t;
typedef uint32_t timer_t_;
#define timer_t timer_t_
typedef uint32_t spi_dev_t;
enum { LOW = 0, HIGH = 1 };
enum { INPUT, OUTPUT, INPUT_PULLUP, INPUT_PULLDOWN, ANALOG, OUTPUT_LOW, OUTPUT_HIGH };
enum { BOTH, RISING, FALLING };
#define NO_PIN ((pin_t)-1)
typedef struct { void *user_data; uint32_t edge; void (*pin_change)(void *user_data, pin_t pin, uint32_t value); } pin_watch_config_t;
typedef struct { void *user_data; pin_t sck, mosi, miso; uint32_t mode; void (*done)(void *user_data, uint8_t *buffer, uint32_t count); } spi_config_t;
typedef struct { void *user_data; void (*callback)(void *user_data); } timer_config_t;
pin_t pin_init(const char *name, uint32_t mode);
void pin_write(pin_t pin, uint32_t value);
uint32_t pin_read(pin_t pin);
bool pin_watch(pin_t pin, pin_watch_config_t *config);
spi_dev_t spi_init(spi_config_t *config);
void spi_start(spi_dev_t spi, uint8_t *buffer, uint32_t count);
void spi_stop(spi_dev_t spi);
timer_t timer_init(timer_config_t *config);
void timer_start(timer_t timer, uint32_t micros, bool repeat);
void timer_stop(timer_t timer);
uint64_t get_sim_nanos(void);
uint32_t attr_init(const char *name, uint32_t default_value);
uint32_t attr_read(uint32_t attr);
void chip_init(void);
#ifdef __cplusplus
}
#endif
