import subprocess
import sys
import unittest


class TestCCPDualInterfaceTestToolkit(unittest.TestCase):
    """Contract: CCPBoundBuffer supports all three binding scenarios —
    owned (own ap-allocated buffer), view (not owned, ap-allocated block
    start), and embedded (interior pointer into a parent block) — driven
    from Python through the CCPDualInterfaceTestToolkit, which exposes the
    cdef-only operations (c_from_header, ccp_bind, ccp_bind_embedded,
    ccp_unbind, header_addr) to the Python test interface.

    CCPBoundBuffer treats its buffer as a NUL-terminated byte string:
    values returns the full size bytes (zero-padded on write), and
    c_from_header derives size via strlen — an interior header measures the
    remaining tail of the parent block.

    Expected behavior:
        - owned: __init__ binds; values round-trip (zero-padded);
          self_dealloc / GC free gracefully.
        - view: c_from_header + ccp_bind shares the owner's buffer; freeing
          the owner releases the view's binding and nulls its header.
        - embedded: interior-pointer wrappers bind via ccp_bind_embedded;
          ref-counts balance on both child-GC-first and parent-free-first.
        - unbound: wrappers never bound deallocate silently.
        - error-proof: a NULL header reports values None, and binding it
          raises BufferError.

    Oracle: the child process must exit 0 with no "[AP_ALLOC_VIGILANT] ERROR"
    and no "Exception ignored" on stderr (failures segfault (139) or abort
    (134)).
    """

    @classmethod
    def _run_in_subprocess(cls, code: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=60,
        )

    def _assert_clean_run(self, code: str) -> None:
        proc = self._run_in_subprocess(code)
        self.assertEqual(proc.returncode, 0, f"stderr:\n{proc.stderr}")
        self.assertNotIn("[AP_ALLOC_VIGILANT] ERROR", proc.stderr)
        self.assertNotIn("Exception ignored", proc.stderr)

    def test_00_owned_bind_and_values_roundtrip(self) -> None:
        """An owned CCPBoundBuffer is bound on construction (address
        non-NULL) and values round-trip zero-padded to the full size."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPBoundBuffer\n"
            "buf = CCPBoundBuffer(16)\n"
            "assert buf.address != 'NULL'\n"
            "buf.values = b'hello'\n"
            "assert buf.values == b'hello' + b'\\x00' * 11\n"
            "del buf\n"
        )

    def test_01_self_dealloc_unbinds_and_frees(self) -> None:
        """self_dealloc() fires DEALLOC, the adaptor releases the binding
        (address becomes 'NULL') and the free completes; a second call is a
        no-op and final GC is silent."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPBoundBuffer\n"
            "array = CCPBoundBuffer(8)\n"
            "array.self_dealloc()\n"
            "assert array.address == 'NULL'\n"
            "array.self_dealloc()\n"
            "assert array.address == 'NULL'\n"
            "del array\n"
        )

    def test_02_gc_frees_owner_gracefully(self) -> None:
        """Garbage-collecting the owning wrapper frees the bound buffer
        without a vigilant abort or dealloc exceptions."""
        self._assert_clean_run(
            "import gc\n"
            "from cbase.allocator_protocol.c_dual_interface import CCPBoundBuffer\n"
            "array = CCPBoundBuffer(8)\n"
            "array.values = b'12345678'\n"
            "del array\n"
            "gc.collect()\n"
        )

    def test_03_many_alloc_free_cycles(self) -> None:
        """Repeated alloc/self_dealloc cycles stay stable (no freelist or
        callback-list corruption across iterations)."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPBoundBuffer\n"
            "for i in range(100):\n"
            "    array = CCPBoundBuffer(8)\n"
            "    array.self_dealloc()\n"
        )

    def test_04_view_wrapper_lifecycle(self) -> None:
        """A view (c_from_header on the owner's block start + ccp_bind)
        shares the buffer; freeing the owner releases the view's binding and
        nulls its header; view GC afterwards is silent."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPBoundBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = CCPBoundBuffer(8)\n"
            "owner.values = b'01234567'\n"
            "view = CCPDualInterfaceTestToolkit.c_from_header(CCPDualInterfaceTestToolkit.header_addr(owner), False)\n"
            "CCPDualInterfaceTestToolkit.ccp_bind(view)\n"
            "assert view.address != 'NULL'\n"
            "assert view.values == b'01234567'\n"
            "view.values = b'abcdefgh'\n"
            "assert owner.values == b'abcdefgh'\n"
            "owner.self_dealloc()\n"
            "assert view.address == 'NULL'\n"
            "assert CCPDualInterfaceTestToolkit.header_addr(view) == 0\n"
            "del view\n"
        )

    def test_05_embedded_wrapper_lifecycle(self) -> None:
        """An embedded entry (interior pointer into the parent block, bound
        via ccp_bind_embedded) measures the remaining tail; writes land in
        the parent; freeing the parent nulls the entry's header."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPBoundBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = CCPBoundBuffer(16)\n"
            "owner.values = b'0123456789'\n"
            "entry = CCPDualInterfaceTestToolkit.embedded_from(owner, 3)\n"
            "assert CCPDualInterfaceTestToolkit.header_addr(entry) == CCPDualInterfaceTestToolkit.header_addr(owner) + 3\n"
            "assert entry.values == b'3456789'\n"
            "entry.values = b'xyz'\n"
            "assert owner.values == b'012xyz' + b'\\x00' * 10\n"
            "owner.self_dealloc()\n"
            "assert entry.address == 'NULL'\n"
            "assert CCPDualInterfaceTestToolkit.header_addr(entry) == 0\n"
            "del entry\n"
        )

    def test_06_embedded_child_gc_before_parent_free(self) -> None:
        """The embedded child releases its binding on GC (ref-count drops
        back to the parent's own); the parent then frees cleanly."""
        self._assert_clean_run(
            "import gc\n"
            "from cbase.allocator_protocol.c_dual_interface import CCPBoundBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = CCPBoundBuffer(8)\n"
            "entry = CCPDualInterfaceTestToolkit.embedded_from(owner, 2)\n"
            "entry.values = b'zz'\n"
            "del entry\n"
            "gc.collect()\n"
            "owner.self_dealloc()\n"
        )

    def test_07_two_step_embedded_bind(self) -> None:
        """The explicit two-step path — c_from_header on an interior pointer
        then ccp_bind_embedded with the parent block address — works."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPBoundBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = CCPBoundBuffer(8)\n"
            "owner.values = b'01234567'\n"
            "entry = CCPDualInterfaceTestToolkit.c_from_header(CCPDualInterfaceTestToolkit.header_addr(owner) + 3, False)\n"
            "CCPDualInterfaceTestToolkit.ccp_bind_embedded(entry, CCPDualInterfaceTestToolkit.header_addr(owner))\n"
            "assert entry.values == b'34567'\n"
            "entry.values = b'zz'\n"
            "assert owner.values == b'012zz' + b'\\x00' * 3\n"
            "owner.self_dealloc()\n"
            "assert CCPDualInterfaceTestToolkit.header_addr(entry) == 0\n"
            "del entry\n"
        )

    def test_08_unbound_wrappers_dealloc_gracefully(self) -> None:
        """Wrappers created WITHOUT ccp_bind / ccp_bind_embedded must still
        deallocate silently: an unbound view, a bare CCPType instance, and
        the parent free."""
        self._assert_clean_run(
            "import gc\n"
            "from cbase.allocator_protocol.c_dual_interface import CCPType, CCPBoundBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = CCPBoundBuffer(8)\n"
            "owner.values = b'01234567'\n"
            "view = CCPDualInterfaceTestToolkit.c_from_header(CCPDualInterfaceTestToolkit.header_addr(owner), False)\n"
            "assert view.values == b'01234567'\n"
            "assert view.address == 'NULL'\n"
            "del view\n"
            "gc.collect()\n"
            "bare = CCPType()\n"
            "del bare\n"
            "gc.collect()\n"
            "owner.self_dealloc()\n"
        )

    def test_09_null_header_bind_raises(self) -> None:
        """A NULL-header wrapper reports values None, and binding it raises
        BufferError (error-proof construction path)."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPDualInterfaceTestToolkit\n"
            "null_view = CCPDualInterfaceTestToolkit.c_from_header(0, False)\n"
            "assert null_view.values is None\n"
            "try:\n"
            "    CCPDualInterfaceTestToolkit.ccp_bind(null_view)\n"
            "    raise AssertionError('expected BufferError')\n"
            "except BufferError:\n"
            "    pass\n"
            "del null_view\n"
        )

    def test_10_ccp_dealloc_triggered_on_self_dealloc(self) -> None:
        """The __ccp_dealloc__ override runs during the DEALLOC pass:
        CCPBoundBuffer zeroes its size field before the header is nulled."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPBoundBuffer\n"
            "buf = CCPBoundBuffer(16)\n"
            "assert buf.size == 16\n"
            "buf.self_dealloc()\n"
            "assert buf.size == 0\n"
            "assert buf.address == 'NULL'\n"
            "del buf\n"
        )

    def test_11_ccp_dealloc_triggered_on_view_invalidation(self) -> None:
        """Owner free fires the hook on every bound wrapper: the view's
        size is zeroed together with the owner's."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPBoundBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = CCPBoundBuffer(8)\n"
            "owner.values = b'01234567'\n"
            "view = CCPDualInterfaceTestToolkit.c_from_header(CCPDualInterfaceTestToolkit.header_addr(owner), False)\n"
            "CCPDualInterfaceTestToolkit.ccp_bind(view)\n"
            "assert view.size == 8\n"
            "owner.self_dealloc()\n"
            "assert owner.size == 0\n"
            "assert view.size == 0\n"
            "assert CCPDualInterfaceTestToolkit.header_addr(view) == 0\n"
            "del view\n"
        )

    def test_12_ccp_dealloc_triggered_on_embedded_invalidation(self) -> None:
        """Embedded wrappers get the hook too: the entry's size is zeroed
        when the parent block frees."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPBoundBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = CCPBoundBuffer(16)\n"
            "owner.values = b'0123456789'\n"
            "entry = CCPDualInterfaceTestToolkit.embedded_from(owner, 3)\n"
            "assert entry.size == 7\n"
            "owner.self_dealloc()\n"
            "assert entry.size == 0\n"
            "assert CCPDualInterfaceTestToolkit.header_addr(entry) == 0\n"
            "del entry\n"
        )


if __name__ == '__main__':
    unittest.main()
