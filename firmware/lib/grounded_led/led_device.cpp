#include "led_device.h"

#include <string.h>

void LedDevice::sendText(const char* text) { write_(text, strlen(text)); }

void LedDevice::sendState() {
  send(pacer_.active() ? led_msg_guide(buf_, pacer_.rhythm(), pacer_.cycles())
                       : led_msg_idle(buf_));
}

void LedDevice::endSession() {
  if (pacer_.active()) send(led_msg_done(buf_, pacer_.rhythm(), pacer_.cyclesDone()));
}

void LedDevice::begin() {
  sendText("#Grounded desk LED\n");
  sendState();
}

void LedDevice::onChar(char c, uint32_t now_ms) {
  const char* line = reader_.feed(c);
  if (line) handle(parse_led_command(line), now_ms);
}

void LedDevice::handle(const LedCommand& cmd, uint32_t now_ms) {
  switch (cmd.type) {
    case LedCommand::GUIDE:
      // Check first, so a bad command doesn't end a session that is running fine
      if (cmd.rhythm >= RHYTHM_COUNT) {
        sendText("!,unknown rhythm\n");
        return;
      }
      endSession();
      pacer_.start(cmd.rhythm, cmd.cycles, now_ms);
      next_rhythm_ = cmd.rhythm;
      sendState();
      break;
    case LedCommand::STOP:
      endSession();
      pacer_.stop();
      sendState();
      break;
    case LedCommand::STATUS:
      sendState();
      break;
    case LedCommand::INVALID:
      sendText("!,bad command\n");
      break;
    case LedCommand::NONE:
      break;
  }
}

void LedDevice::onButton(uint32_t now_ms) {
  // Idle: start the last used rhythm. Guiding: switch to the next rhythm.
  if (pacer_.active()) {
    next_rhythm_ = pacer_.rhythm() + 1;
    if (next_rhythm_ == RHYTHM_COUNT) next_rhythm_ = 0;
    endSession();
  }
  pacer_.start(next_rhythm_, BUTTON_CYCLES, now_ms);
  send(led_msg_button(buf_, next_rhythm_));
  sendState();
}

void LedDevice::tick(uint32_t now_ms) {
  const uint8_t ev = pacer_.update(now_ms);
  if (ev & BreathPacer::EV_DONE) {
    send(led_msg_done(buf_, pacer_.rhythm(), pacer_.cyclesDone()));
    sendState();
  } else if (ev & BreathPacer::EV_PHASE) {
    sendText("#");
    sendText(PHASE_NAMES[pacer_.phase()]);
    sendText("\n");
  }
}
