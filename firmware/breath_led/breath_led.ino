const uint32_t LED_PIN = D6;
const uint32_t PWM_FREQ_HZ = 1000;
const uint32_t PWM_MAX  = 4095; //resolutin_12b - needs to match
const float MIN_LEVEL = 0.02f; // led stays active during period
const uint32_t UPDATE_MS = 10; //5-20 ideal
const uint32_t BUTTON_PIN = D2;
const uint32_t DEBOUNCE_MS = 30;


enum Phase {INHALE, HOLD_IN, EXHALE, HOLD_OUT, PHASE_COUNT};
const char* const PHASE_NAMES[] = {"INHALE", "HOLD_IN", "EXHALE", "HOLD_OUT"};
static_assert(sizeof(PHASE_NAMES) / sizeof(PHASE_NAMES[0]) == PHASE_COUNT,
              "PHASE_NAMES and PHASE needs to have same number of elements!");

struct Rhythm {
  const char* name;
  uint32_t ms[PHASE_COUNT];
};

const Rhythm RHYTHMS[] = {
  {"Box 4-4-4-4", {4000,4000,4000,4000}},
  {"4-7-8", {4000,7000,8000,0}},
  {"Relax 4-0-6-0", {4000,0,6000,0}},
};

const uint8_t RHYTHM_COUNT = sizeof(RHYTHMS) /sizeof(RHYTHMS[0]);

uint8_t rhythm = 0;
Phase phase = INHALE;
uint32_t phaseStart = 0;
uint32_t lastUpdate = 0;

volatile bool buttonPending = false;
volatile uint32_t buttonTimeMs = 0;

HardwareTimer* pwmTimer;
uint32_t pwmChannel;

void setupPwm() {
  PinName pin = digitalPinToPinName(LED_PIN);
  TIM_TypeDef* instance = (TIM_TypeDef*)pinmap_peripheral(pin, PinMap_PWM);
  pwmChannel = STM_PIN_CHANNEL(pinmap_function(pin, PinMap_PWM));

  if (instance == NULL) {
    Serial.println("Error: No PWM on this pin");
    while (true) {}
  }

  pwmTimer = new HardwareTimer(instance);
  pwmTimer->setMode(pwmChannel, TIMER_OUTPUT_COMPARE_PWM1, LED_PIN);
  pwmTimer->setOverflow(PWM_FREQ_HZ, HERTZ_FORMAT);
  pwmTimer->setCaptureCompare(pwmChannel, 0, RESOLUTION_12B_COMPARE_FORMAT);
  pwmTimer->resume();
}

void writeLevel(float level) {
  float corrected = level*level;
  uint32_t ccr = (uint32_t)(corrected * PWM_MAX + 0.5f);
  pwmTimer->setCaptureCompare(pwmChannel, ccr, RESOLUTION_12B_COMPARE_FORMAT);
}
float easeInOut(float t) {
  return t * t * (3.0f - 2.0f * t); //smoothstep
}
float levelFor(Phase p, float t) {
  float e;
  switch (p) {
    case INHALE: e = easeInOut(t); break;
    case HOLD_IN: e = 1.0f; break;
    case EXHALE: e = 1.0f - easeInOut(t); break;
    case HOLD_OUT:
    default: e = 0.0f; break;
  }
  return MIN_LEVEL + (1.0f - MIN_LEVEL) * e;
}
uint32_t phaseDuration(){
  return RHYTHMS[rhythm].ms[phase];
}
  
void onButtonEdge(){
  buttonTimeMs = millis();
  buttonPending = true;
}


void setup() {
   Serial.begin(115200);
   setupPwm();

   pinMode(BUTTON_PIN, INPUT_PULLUP);
   attachInterrupt(digitalPinToInterrupt(BUTTON_PIN), onButtonEdge, FALLING);

   phaseStart = millis();
   Serial.print("Rhythm: ");
   Serial.println(RHYTHMS[rhythm].name);
   Serial.println(PHASE_NAMES[phase]);
}
void loop() {
  uint32_t now = millis();

  if (buttonPending && (now - buttonTimeMs >= DEBOUNCE_MS)) {
    buttonPending = false;
    if (digitalRead(BUTTON_PIN)== LOW) {
      rhythm = (rhythm + 1) % RHYTHM_COUNT;
      phase = INHALE;
      phaseStart = now;
      Serial.print("Rhythm: ");
      Serial.println(RHYTHMS[rhythm].name);
      Serial.println(PHASE_NAMES[phase]);
    }
  }
  Phase oldPhase = phase;
  while (now - phaseStart >= phaseDuration()){
    phaseStart += phaseDuration();
    phase = (Phase)((phase + 1) % PHASE_COUNT);
  }
  if (phase != oldPhase){
    Serial.println(PHASE_NAMES[phase]);
  }
    
  if (now - lastUpdate >= UPDATE_MS) {
    lastUpdate = now;
    uint32_t dur = phaseDuration();
    float t = (dur==0) ? 1.0f : (float)(now - phaseStart) / dur;
    if (t > 1.0f) t = 1.0f;
    writeLevel(levelFor(phase, t));
  }
}