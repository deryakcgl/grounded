CXX      ?= clang++
CXXFLAGS := -std=c++17 -O2 -Wall -Wextra -Wdouble-promotion -ffp-contract=off
DSP      := ../lib/grounded_dsp
LED      := ../lib/grounded_led
ADS      := ../lib/ads1292r
DSP_SRC  := $(DSP)/breath_detector.cpp $(DSP)/beat_detector.cpp
POD_SRC  := $(DSP_SRC) $(DSP)/pod_pipeline.cpp $(ADS)/ads1292r.cpp
LED_SRC  := $(LED)/breath_pacer.cpp $(LED)/led_protocol.cpp $(LED)/led_device.cpp

all: dsp_test led_test led_sim ads_test pod_sim wokwi_chip_sim

dsp_test: main.cpp $(DSP_SRC) $(wildcard $(DSP)/*.h)
	$(CXX) $(CXXFLAGS) -I$(DSP) -o $@ main.cpp $(DSP_SRC)

led_test: led_test.cpp $(LED_SRC) $(wildcard $(LED)/*.h)
	$(CXX) $(CXXFLAGS) -I$(LED) -o $@ led_test.cpp $(LED_SRC)

led_sim: led_sim.cpp $(LED_SRC) $(wildcard $(LED)/*.h)
	$(CXX) $(CXXFLAGS) -I$(LED) -o $@ led_sim.cpp $(LED_SRC)

ads_test: ads_test.cpp fake_ads1292r.h $(ADS)/ads1292r.cpp $(wildcard $(ADS)/*.h)
	$(CXX) $(CXXFLAGS) -I$(ADS) -o $@ ads_test.cpp $(ADS)/ads1292r.cpp

pod_sim: pod_sim.cpp fake_ads1292r.h $(POD_SRC) $(wildcard $(ADS)/*.h) $(wildcard $(DSP)/*.h)
	$(CXX) $(CXXFLAGS) -I$(DSP) -I$(ADS) -o $@ pod_sim.cpp $(POD_SRC)

CHIP     := ../grounded_pod/wokwi/ads1292r.chip.c
wokwi_chip_sim: wokwi_chip_sim.cpp $(CHIP) wokwi_stub/wokwi-api.h $(POD_SRC)
	clang -std=c11 -O2 -Wall -Wextra -Iwokwi_stub -c -o ads1292r_chip.o $(CHIP)
	$(CXX) $(CXXFLAGS) -I$(DSP) -I$(ADS) -Iwokwi_stub -o $@ wokwi_chip_sim.cpp ads1292r_chip.o $(POD_SRC)
	rm -f ads1292r_chip.o

test: led_test ads_test
	./led_test && ./ads_test

clean:
	rm -f dsp_test led_test led_sim ads_test pod_sim wokwi_chip_sim

.PHONY: all test clean
