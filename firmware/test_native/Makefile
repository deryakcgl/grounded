# grounded_dsp'yi Mac'te derler. -Wdouble-promotion: float yerine yanlislikla
# double kullanilirsa uyarir (FPU'suz STM32'de double cok pahali).
CXX      ?= clang++
# -ffp-contract=off: Mac (arm64) carpma+toplamayi tek adimda (FMA) yapabilir, Cortex-M0+
# yapamaz. Kapatinca iki taraf bit bit ayni sonucu verir.
CXXFLAGS := -std=c++17 -O2 -Wall -Wextra -Wdouble-promotion -ffp-contract=off -I../lib/grounded_dsp
SRC      := main.cpp ../lib/grounded_dsp/breath_detector.cpp ../lib/grounded_dsp/beat_detector.cpp

dsp_test: $(SRC) $(wildcard ../lib/grounded_dsp/*.h)
	$(CXX) $(CXXFLAGS) -o $@ $(SRC)

clean:
	rm -f dsp_test

.PHONY: clean
