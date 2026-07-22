cdef extern from "cbase/int128.h":
    ctypedef unsigned long long uint128_t
    ctypedef long long int128_t

    const uint128_t UINT128_MAX
    const int128_t INT128_MAX
    const int128_t INT128_MIN

    uint128_t c_read_uint128(const void* data)
    void      c_write_uint128(void* data, uint128_t value)
    int128_t  c_read_int128(const void* data)
    void      c_write_int128(void* data, int128_t value)

    int c_u128_cmp(uint128_t v1, uint128_t v2)
    int c_i128_cmp(int128_t v1, int128_t v2)
