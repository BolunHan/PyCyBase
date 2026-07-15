#ifndef TIME_SCHED_NT_COMPAT_H
#define TIME_SCHED_NT_COMPAT_H

#ifndef _WIN32
#error "time_sched_nt_compat.h is intended for Windows builds only"
#endif

#include <time.h>

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

#ifndef CLOCK_REALTIME
#define CLOCK_REALTIME 0
#endif

static inline int clock_gettime(int clock_id, struct timespec* ts) {
    (void) clock_id;
    if (!ts) {
        return -1;
    }

    return timespec_get(ts, TIME_UTC) == TIME_UTC ? 0 : -1;
}

static inline void sched_yield(void) {
    SwitchToThread();
}

#endif /* TIME_SCHED_NT_COMPAT_H */