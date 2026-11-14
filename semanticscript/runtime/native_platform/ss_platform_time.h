#ifndef SS_PLATFORM_TIME_H
#define SS_PLATFORM_TIME_H

#ifdef __cplusplus
extern "C" {
#endif

long long ss_platform_wall_time_ms(void);
long long ss_platform_monotonic_ms(void);
void ss_platform_sleep_ms(unsigned int milliseconds);

#ifdef __cplusplus
}
#endif

#endif
