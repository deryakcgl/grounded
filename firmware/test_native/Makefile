# Builds the firmware libraries on the Mac. -Wdouble-promotion: warns if double is used by accident
# instead of float (double is very expensive on an STM32 without an FPU).
CXX      ?= clang++
# -ffp-contract=off: the Mac (arm64) can fuse multiply+add into one step (FMA), the Cortex-M0+
# cannot. Turning it off makes both sides produce bit-identical results.
CXXFLAGS := -std=c++17 -O2 -Wall -Wextra -Wdouble-promotion -ffp-contract=off
DSP      := ../lib/grounded_dsp
LED      := ../lib/grounded_led
DSP_SRC  := $(DSP)/breath_detector.cpp $(DSP)/beat_detector.cpp
LED_SRC  := $(LED)/breath_pacer.cpp $(LED)/led_protocol.cpp $(LED)/led_device.cpp

all: dsp_test led_test led_sim

dsp_test: main.cpp $(DSP_SRC) $(wildcard $(DSP)/*.h)
	$(CXX) $(CXXFLAGS) -I$(DSP) -o $@ main.cpp $(DSP_SRC)

led_test: led_test.cpp $(LED_SRC) $(wildcard $(LED)/*.h)
	$(CXX) $(CXXFLAGS) -I$(LED) -o $@ led_test.cpp $(LED_SRC)

led_sim: led_sim.cpp $(LED_SRC) $(wildcard $(LED)/*.h)
	$(CXX) $(CXXFLAGS) -I$(LED) -o $@ led_sim.cpp $(LED_SRC)

test: led_test
	./led_test

clean:
	rm -f dsp_test led_test led_sim

.PHONY: all test clean
