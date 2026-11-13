// Desk breathing LED.
//   Idle:     faint glow.
//   Guiding:  the LED rises and falls with a breathing rhythm for N cycles, then goes idle.
// A session starts from the host (serial command, see grounded_led/led_protocol.h) or with
// the button (idle: start; guiding: next rhythm).
//
// This file is only the hardware glue: serial characters, the button and the PWM output.
// The behaviour lives in lib/grounded_led (LedDevice), which the Mac's virtual LED also runs.
#include "led_device.h"

const uint32_t LED_PIN = D6;
const uint32_t PWM_FREQ_HZ = 1000;
const uint32_t PWM_MAX = 4095;   // 12-bit resolution - must match RESOLUTION_12B below
const uint32_t UPDATE_MS = 10;   // LED refresh: 5-20 ms looks smooth
const uint32_t BUTTON_PIN = D2;
const uint32_t DEBOUNCE_MS = 30;

volatile bool buttonPending = false;
volatile uint32_t buttonTimeMs = 0;

HardwareTimer* pwmTimer;
uint32_t pwmChannel;
uint32_t lastUpdate = 0;

void serialWrite(const char* text, size_t len) { Serial.write(text, len); }

LedDevice device(serialWrite);

void setupPwm() {
  PinName pin = digitalPinToPinName(LED_PIN);
  TIM_TypeDef* instance = (TIM_TypeDef*)pinmap_peripheral(pin, PinMap_PWM);
  pwmChannel = STM_PIN_CHANNEL(pinmap_function(pin, PinMap_PWM));

  if (instance == NULL) {
    Serial.println("!,no PWM on this pin");
    while (true) {}
  }

  pwmTimer = new HardwareTimer(instance);
  pwmTimer->setMode(pwmChannel, TIMER_OUTPUT_COMPARE_PWM1, LED_PIN);
  pwmTimer->setOverflow(PWM_FREQ_HZ, HERTZ_FORMAT);
  pwmTimer->setCaptureCompare(pwmChannel, 0, RESOLUTION_12B_COMPARE_FORMAT);
  pwmTimer->resume();
}

// level is perceptual brightness 0..1; squaring approximates the eye's gamma
void writeLevel(float level) {
  float corrected = level * level;
  uint32_t ccr = (uint32_t)(corrected * PWM_MAX + 0.5f);
  pwmTimer->setCaptureCompare(pwmChannel, ccr, RESOLUTION_12B_COMPARE_FORMAT);
}

void onButtonEdge() {
  buttonTimeMs = millis();
  buttonPending = true;
}

void setup() {
  Serial.begin(115200);
  setupPwm();
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(BUTTON_PIN), onButtonEdge, FALLING);
  device.begin();
}

void loop() {
  uint32_t now = millis();

  while (Serial.available()) {
    device.onChar((char)Serial.read(), now);
  }

  if (buttonPending && (now - buttonTimeMs >= DEBOUNCE_MS)) {
    buttonPending = false;
    if (digitalRead(BUTTON_PIN) == LOW) device.onButton(now);
  }

  device.tick(now);

  if (now - lastUpdate >= UPDATE_MS) {
    lastUpdate = now;
    writeLevel(device.level(now));
  }
}
