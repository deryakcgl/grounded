# Builds grounded_dsp on the Mac. -Wdouble-promotion: warns if double is used by accident
# instead of float (double is very expensive on an STM32 without an FPU).
CXX      ?= clang++
# -ffp-contract=off: the Mac (arm64) can fuse multiply+add into one step (FMA), the Cortex-M0+
# cannot. Turning it off makes both sides produce bit-identical results.
CXXFLAGS := -std=c++17 -O2 -Wall -Wextra -Wdouble-promotion -ffp-contract=off -I../lib/grounded_dsp
SRC      := main.cpp ../lib/grounded_dsp/breath_detector.cpp ../lib/grounded_dsp/beat_detector.cpp

dsp_test: $(SRC) $(wildcard ../lib/grounded_dsp/*.h)
	$(CXX) $(CXXFLAGS) -o $@ $(SRC)

clean:
	rm -f dsp_test

.PHONY: clean
