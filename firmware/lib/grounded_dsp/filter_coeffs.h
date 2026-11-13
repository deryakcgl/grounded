#pragma once

#define RESP_FS 25
#define RESP_SOS_N 2
static const float RESP_SOS[2][6] = {
    {0.0121519606f, 0.0243039213f, 0.0121519606f, 1.0f, -1.67663093f, 0.726108624f},
    {1.0f, -2.0f, 1.0f, 1.0f, -1.9824061f, 0.982577908f}
};

static const float BREATH_ALPHA_FAST = 0.00995016625f;
static const float BREATH_ALPHA_SLOW = 0.000666444494f;

#define ECG_FS 250
#define ECG_SOS_N 2
static const float ECG_SOS[2][6] = {
    {0.0133592f, 0.0267184001f, 0.0133592f, 1.0f, -1.68135386f, 0.779892144f},
    {1.0f, -2.0f, 1.0f, 1.0f, -1.8795936f, 0.898709888f}
};

static const float BEAT_ALPHA_NOISE = 0.00399201066f;
