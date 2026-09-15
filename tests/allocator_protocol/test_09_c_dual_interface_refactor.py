import subprocess
import sys
import unittest

from cbase.allocator_protocol.c_dual_interface import (
    CCPBoundBuffer,
    CCPDualInterfaceTestToolkit,
)

TK = CCPDualInterfaceTestToolkit


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
        - view: c_from_header adopts a block start and binds inside;
          freeing the owner releases the view's binding and nulls its
          header.
        - embedded: c_from_header_embedded adopts an interior pointer and
          binds embedded inside; ref-counts balance on both child-GC-first
          and parent-free-first.
        - unbound: __new__-only wrappers (never bound) deallocate
          silently.
        - error-proof: an unbound wrapper reports values None, and
          binding it raises BufferError.
        - address: the wrapper's OWN header address — the block start for
          a block-start bind, the interior pointer for an embedded bind —
          and 'NULL' when unbound; ``embedded`` reports which of the two
          it is (BufferError when unbound).

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
        """self_dealloc() fires FREE, the adaptor releases the binding
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
        """A view (c_from_header on the owner's block start) is bound at
        adoption; freeing the owner releases the view's binding and nulls
        its header; view GC afterwards is silent."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPBoundBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = CCPBoundBuffer(8)\n"
            "owner.values = b'01234567'\n"
            "view = CCPDualInterfaceTestToolkit.c_from_header(CCPDualInterfaceTestToolkit.header_addr(owner), False)\n"
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
            "assert int(entry.address, 16) == CCPDualInterfaceTestToolkit.header_addr(entry)\n"
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

    def test_07_embedded_adoption_helper(self) -> None:
        """c_from_header_embedded adopts an interior pointer and binds it
        embedded (with the parent block start) inside — no caller-side
        bind; writes land in the owner."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPBoundBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = CCPBoundBuffer(8)\n"
            "owner.values = b'01234567'\n"
            "entry = CCPDualInterfaceTestToolkit.c_from_header_embedded(CCPDualInterfaceTestToolkit.header_addr(owner) + 3, CCPDualInterfaceTestToolkit.header_addr(owner))\n"
            "assert int(entry.address, 16) == CCPDualInterfaceTestToolkit.header_addr(owner) + 3\n"
            "assert entry.values == b'34567'\n"
            "entry.values = b'zz'\n"
            "assert owner.values == b'012zz' + b'\\x00' * 3\n"
            "owner.self_dealloc()\n"
            "assert CCPDualInterfaceTestToolkit.header_addr(entry) == 0\n"
            "del entry\n"
        )

    def test_08_unbound_wrappers_dealloc_gracefully(self) -> None:
        """Wrappers that never gained a binding — a __new__-only wrapper
        and a bare CCPType — deallocate silently, and the parent free
        completes."""
        self._assert_clean_run(
            "import gc\n"
            "from cbase.allocator_protocol.c_dual_interface import CCPType, CCPBoundBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = CCPBoundBuffer(8)\n"
            "owner.values = b'01234567'\n"
            "null_view = CCPDualInterfaceTestToolkit.new_unbound()\n"
            "assert null_view.values is None\n"
            "assert null_view.address == 'NULL'\n"
            "del null_view\n"
            "gc.collect()\n"
            "bare = CCPType()\n"
            "del bare\n"
            "gc.collect()\n"
            "owner.self_dealloc()\n"
        )

    def test_09_null_header_bind_raises(self) -> None:
        """An unbound (header-NULL) wrapper reports values None, and
        binding it raises BufferError (error-proof construction path)."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPDualInterfaceTestToolkit\n"
            "null_view = CCPDualInterfaceTestToolkit.new_unbound()\n"
            "assert null_view.values is None\n"
            "try:\n"
            "    CCPDualInterfaceTestToolkit.ccp_bind(null_view)\n"
            "    raise AssertionError('expected BufferError')\n"
            "except BufferError:\n"
            "    pass\n"
            "del null_view\n"
        )

    def test_10_ccp_dealloc_triggered_on_self_dealloc(self) -> None:
        """The __ccp_dealloc__ override runs during the FREE pass:
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

    def _assert_abort_run(self, code: str) -> None:
        proc = self._run_in_subprocess(code)
        self.assertEqual(proc.returncode, -6, f"stderr:\n{proc.stderr}")
        self.assertIn("[CCP] ERROR", proc.stderr)
        self.assertIn("double", proc.stderr)

    def test_13_double_bind_on_owned_aborts(self) -> None:
        """A second ccp_bind on an already-bound wrapper aborts (SIGABRT)
        with a [CCP] ERROR message on stderr — the ctx must be fresh (the
        zeroed allocation guarantees ap_header == NULL on first bind)."""
        self._assert_abort_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPBoundBuffer, CCPDualInterfaceTestToolkit\n"
            "array = CCPBoundBuffer(8)\n"
            "CCPDualInterfaceTestToolkit.ccp_bind(array)\n"
        )

    def test_14_double_bind_after_adoption_aborts(self) -> None:
        """c_from_header already binds inside — an explicit ccp_bind
        afterwards is a double bind and aborts."""
        self._assert_abort_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPBoundBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = CCPBoundBuffer(8)\n"
            "view = CCPDualInterfaceTestToolkit.c_from_header(CCPDualInterfaceTestToolkit.header_addr(owner), False)\n"
            "CCPDualInterfaceTestToolkit.ccp_bind(view)\n"
        )

    def test_15_double_bind_embedded_aborts(self) -> None:
        """c_from_header_embedded already binds embedded inside — an
        explicit ccp_bind_embedded afterwards aborts."""
        self._assert_abort_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPBoundBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = CCPBoundBuffer(8)\n"
            "entry = CCPDualInterfaceTestToolkit.c_from_header_embedded(CCPDualInterfaceTestToolkit.header_addr(owner) + 1, CCPDualInterfaceTestToolkit.header_addr(owner))\n"
            "CCPDualInterfaceTestToolkit.ccp_bind_embedded(entry, CCPDualInterfaceTestToolkit.header_addr(owner))\n"
        )


class TestCCPAddressContract(unittest.TestCase):
    """Contract: ``CCPType.address`` reports the wrapper's OWN bound C
    header — read from the header field slot at
    ``(char*)<PyObject*>self + ccp_header_offset``, the same slot the FREE
    pass nulls — NOT the bound protocol's buffer. The two coincide for a
    block-start bind and DIFFER for an embedded bind, where the protocol
    belongs to the PARENT block while the header is an interior pointer.

    Expected behavior:
        - owned / block-start view / child block: address == header_addr.
        - embedded: address == parent block start + index, and != the
          parent's own address (regression guard: the property used to
          report the parent's block).
        - husked, never-bound and manually unbound wrappers report 'NULL';
          a manual unbind leaves the header field itself intact.

    Oracle: the toolkit's header_addr() is the C-side ground truth of the
    header field; address is parsed back from its hex string.
    """

    def test_00_owned_and_view_report_the_block_start(self) -> None:
        """An owned wrapper and a block-start view report the block start."""
        owner = CCPBoundBuffer(16)
        view = TK.c_from_header(TK.header_addr(owner), False)

        self.assertEqual(int(owner.address, 16), TK.header_addr(owner))
        self.assertEqual(int(view.address, 16), TK.header_addr(view))
        self.assertEqual(TK.header_addr(view), TK.header_addr(owner))

    def test_01_embedded_reports_the_interior_pointer(self) -> None:
        """An embedded wrapper reports its own interior pointer — not the
        parent block its binding protocol belongs to."""
        owner = CCPBoundBuffer(16)
        entry = TK.embedded_from(owner, 3)
        owner_addr = TK.header_addr(owner)

        self.assertEqual(TK.header_addr(entry), owner_addr + 3)
        self.assertEqual(int(entry.address, 16), TK.header_addr(entry))
        self.assertNotEqual(int(entry.address, 16), owner_addr)

    def test_02_child_block_reports_its_own_start(self) -> None:
        """A child block reports its own start, not its parent's."""
        parent = CCPBoundBuffer(64)
        child = parent.alloc_child(16)

        self.assertEqual(int(child.address, 16), TK.header_addr(child))
        self.assertNotEqual(TK.header_addr(child), TK.header_addr(parent))

    def test_03_husk_and_never_bound_report_null(self) -> None:
        """Husked wrappers (owner freed) and never-bound wrappers report
        'NULL'."""
        owner = CCPBoundBuffer(16)
        view = TK.c_from_header(TK.header_addr(owner), False)
        entry = TK.embedded_from(owner, 3)
        never_bound = TK.new_unbound()

        owner.free_owned()

        for wrapper in (owner, view, entry, never_bound):
            self.assertEqual(wrapper.address, 'NULL')

    def test_04_manual_unbind_nulls_address_keeps_header(self) -> None:
        """A manual unbind releases the binding only: address reports
        'NULL' while the header field itself stays intact — and the later
        owner free no longer nulls it (the wrapper is unregistered)."""
        owner = CCPBoundBuffer(16)
        view = TK.c_from_header(TK.header_addr(owner), False)
        view_addr = TK.header_addr(view)

        TK.ccp_unbind(view)

        self.assertEqual(view.address, 'NULL')
        with self.assertRaises(BufferError):
            view.embedded
        self.assertEqual(TK.header_addr(view), view_addr)
        owner.free_owned()
        self.assertEqual(TK.header_addr(view), view_addr)

    def test_05_embedded_flag_distinguishes_interior_headers(self) -> None:
        """The embedded flag marks interior-pointer binds: False for every
        block-start role (owned, view, child), True for an embedded entry —
        and BufferError once unbound (husked or never bound)."""
        owner = CCPBoundBuffer(64)
        view = TK.c_from_header(TK.header_addr(owner), False)
        child = owner.alloc_child(16)
        entry = TK.embedded_from(owner, 3)

        self.assertFalse(owner.embedded)
        self.assertFalse(view.embedded)
        self.assertFalse(child.embedded)
        self.assertTrue(entry.embedded)

        owner.free_owned()

        for wrapper in (owner, view, entry, child, TK.new_unbound()):
            with self.assertRaises(BufferError):
                wrapper.embedded


class TestCCPBoundBufferValueEdges(unittest.TestCase):
    """Contract: the values accessor/setter edges of the NUL-terminated
    byte-string model, plus the size semantics of the binding roles.

    Expected behavior:
        - a write longer than the buffer truncates to size;
        - a shorter write zero-pads the remainder;
        - an empty write raises RuntimeError;
        - write-after-husk raises BufferError, read-after-husk is None;
        - embedded_from rejects an out-of-range index with IndexError;
        - sizes: owned == requested, embedded view == remaining tail.

    Oracle: byte-exact reads and the documented exception types.
    """

    def test_00_setter_truncates_and_zero_pads(self) -> None:
        """Over-long writes truncate; short writes zero-pad."""
        buf = CCPBoundBuffer(8)
        buf.values = b'x' * 100
        self.assertEqual(buf.values, b'x' * 8)
        buf.values = b'ab'
        self.assertEqual(buf.values, b'ab' + b'\x00' * 6)

    def test_01_setter_rejects_empty_value(self) -> None:
        """An empty write is rejected."""
        buf = CCPBoundBuffer(8)
        with self.assertRaises(RuntimeError):
            buf.values = b''

    def test_02_husk_reads_none_and_rejects_writes(self) -> None:
        """A husked wrapper reads None and refuses writes."""
        buf = CCPBoundBuffer(8)
        buf.free_owned()
        self.assertIsNone(buf.values)
        with self.assertRaises(BufferError):
            buf.values = b'ab'

    def test_03_sizes_and_embedded_index_guard(self) -> None:
        """Owned size is the requested size, an embedded view measures the
        remaining tail, and an out-of-range index raises IndexError."""
        owner = CCPBoundBuffer(16)
        owner.values = b'0123456789'
        entry = TK.embedded_from(owner, 3)

        self.assertEqual(owner.size, 16)
        self.assertEqual(entry.size, 7)
        self.assertEqual(entry.values, b'3456789')
        with self.assertRaises(IndexError):
            TK.embedded_from(owner, 16)


if __name__ == '__main__':
    unittest.main()
