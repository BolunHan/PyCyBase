from .c_intern_string cimport (
    InternString,
    InternStringPool,
    C_POOL, POOL,
    C_INTRA_POOL, INTRA_POOL,
    istr_map,
    c_istr_map_new,
    c_istr_map_free,
    c_istr,
    c_istr_synced,
)
