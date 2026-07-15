#ifndef PTHREAD_NT_COMPAT_H
#define PTHREAD_NT_COMPAT_H

#ifndef _WIN32
#error "pthread_nt_compat.h is intended for Windows builds only"
#endif

#include <errno.h>
#include <limits.h>
#include <time.h>

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

typedef CRITICAL_SECTION   pthread_mutex_t;
typedef void               pthread_mutexattr_t;
typedef CONDITION_VARIABLE pthread_cond_t;
typedef void               pthread_condattr_t;

static inline DWORD pthread_nt_timeout_ms(const struct timespec* abstime) {
    if (!abstime) return INFINITE;

    struct timespec now;
    if (timespec_get(&now, TIME_UTC) != TIME_UTC) return 0;

    time_t sec  = abstime->tv_sec - now.tv_sec;
    long   nsec = abstime->tv_nsec - now.tv_nsec;
    if (nsec < 0) { sec -= 1; nsec += 1000000000L; }
    if (sec < 0 || (sec == 0 && nsec <= 0)) return 0;

    unsigned long long ms = (unsigned long long) sec * 1000ULL;
    ms += (unsigned long long) ((nsec + 999999L) / 1000000L);
    if (ms > (unsigned long long) INFINITE - 1ULL) return INFINITE - 1;
    return (DWORD) ms;
}

static inline int pthread_mutex_init(pthread_mutex_t* mutex, const pthread_mutexattr_t* attr) {
    (void) attr;
    if (!mutex) return EINVAL;
    InitializeCriticalSection(mutex);
    return 0;
}

static inline int pthread_mutex_lock(pthread_mutex_t* mutex) {
    if (!mutex) return EINVAL;
    EnterCriticalSection(mutex);
    return 0;
}

static inline int pthread_mutex_unlock(pthread_mutex_t* mutex) {
    if (!mutex) return EINVAL;
    LeaveCriticalSection(mutex);
    return 0;
}

static inline int pthread_mutex_destroy(pthread_mutex_t* mutex) {
    if (!mutex) return EINVAL;
    DeleteCriticalSection(mutex);
    return 0;
}

static inline int pthread_cond_init(pthread_cond_t* cond, const pthread_condattr_t* attr) {
    (void) attr;
    if (!cond) return EINVAL;
    InitializeConditionVariable(cond);
    return 0;
}

static inline int pthread_cond_wait(pthread_cond_t* cond, pthread_mutex_t* mutex) {
    if (!cond || !mutex) return EINVAL;
    if (SleepConditionVariableCS(cond, mutex, INFINITE)) return 0;
    return EINVAL;
}

static inline int pthread_cond_timedwait(pthread_cond_t* cond, pthread_mutex_t* mutex, const struct timespec* abstime) {
    if (!cond || !mutex) return EINVAL;
    DWORD timeout_ms = pthread_nt_timeout_ms(abstime);
    if (SleepConditionVariableCS(cond, mutex, timeout_ms)) return 0;
    if (GetLastError() == ERROR_TIMEOUT) return ETIMEDOUT;
    return EINVAL;
}

static inline int pthread_cond_signal(pthread_cond_t* cond) {
    if (!cond) return EINVAL;
    WakeConditionVariable(cond);
    return 0;
}

static inline int pthread_cond_broadcast(pthread_cond_t* cond) {
    if (!cond) return EINVAL;
    WakeAllConditionVariable(cond);
    return 0;
}

static inline int pthread_cond_destroy(pthread_cond_t* cond) {
    (void) cond;
    return 0;
}

#endif /* PTHREAD_NT_COMPAT_H */
