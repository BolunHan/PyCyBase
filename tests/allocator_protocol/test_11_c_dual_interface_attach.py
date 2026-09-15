import subprocess
import sys
import unittest

from cbase.allocator_protocol.c_dual_interface import (
    CCPAttachedBuffer,
    CCPDualInterfaceTestToolkit,
)

TK = CCPDualInterfaceTestToolkit


class TestCCPAttachmentProtocol(unittest.TestCase):
    """Contract: the CCP attachment protocol binds a wrapper through an
    embedded ccp_ctx VALUE field (no CCPType inheritance, no ccp_protocol
    cast) — usable by classes that cannot inherit CCPType.

    - BoundBuffer is the plain c-dual-interface design: owner flag only, no
      reverse dealloc invalidation (views are raw pointers).
    - CCPAttachedBuffer(BoundBuffer) embeds ``cdef ccp_ctx ccp_ctx``;
      ccp_attach runs after every init, and the adoption helpers attach
      INSIDE (c_from_header for block starts, c_from_header_embedded for
      interior pointers); the FREE pass detaches the wrapper, runs the
      armed __ccp_dealloc__ hook (zeroes size), and nulls the header.
    - CCPType itself stays bound-only (ccp_bind family).

    Expected behavior:
        - attached owned buffers round-trip values and free gracefully;
          every attached wrapper of the block is husked on the owner free.
        - the attachment works across a plain (unbound) owner, an attached
          owner, interior pointers (attach_embedded), and child blocks.
        - manual detach releases only the binding (header stays intact);
          unattached and NULL-header wrappers dealloc / raise gracefully.
        - bound and attached wrappers coexist on the same block.
        - address: the wrapper's OWN header address — the block start for
          a block-start attach, the interior pointer for an embedded
          attach — and 'NULL' when detached; ``embedded`` reports which of
          the two it is (BufferError when detached).

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

    def test_00_attached_owned_roundtrip(self) -> None:
        """An owned CCPAttachedBuffer is attached on construction (address
        non-NULL) and values round-trip zero-padded to the full size."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPAttachedBuffer\n"
            "buf = CCPAttachedBuffer(16)\n"
            "assert buf.address != 'NULL'\n"
            "buf.values = b'hello'\n"
            "assert buf.values == b'hello' + b'\\x00' * 11\n"
            "del buf\n"
        )

    def test_01_attached_free_owned_husks_self(self) -> None:
        """free_owned() fires FREE: the adaptor detaches the wrapper (address
        'NULL'), the __ccp_dealloc__ hook zeroes size, and the header is
        nulled; a second call is a no-op and final GC is silent."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPAttachedBuffer, CCPDualInterfaceTestToolkit\n"
            "array = CCPAttachedBuffer(8)\n"
            "array.values = b'12345678'\n"
            "array.free_owned()\n"
            "assert array.address == 'NULL'\n"
            "assert array.size == 0\n"
            "assert CCPDualInterfaceTestToolkit.attached_header_addr(array) == 0\n"
            "array.free_owned()\n"
            "assert array.address == 'NULL'\n"
            "del array\n"
        )

    def test_02_attached_view_of_plain_buffer(self) -> None:
        """An attached view over a PLAIN (unbound) BoundBuffer owner shares
        the buffer; freeing the owner detaches the view and nulls its
        header; view GC afterwards is silent."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import BoundBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = BoundBuffer(8)\n"
            "owner.values = b'01234567'\n"
            "view = CCPDualInterfaceTestToolkit.attached_c_from_header(CCPDualInterfaceTestToolkit.buffer_header_addr(owner), False)\n"
            "assert view.address != 'NULL'\n"
            "assert view.values == b'01234567'\n"
            "view.values = b'abcdefgh'\n"
            "assert owner.values == b'abcdefgh'\n"
            "owner.free_owned()\n"
            "assert view.address == 'NULL'\n"
            "assert view.size == 0\n"
            "assert CCPDualInterfaceTestToolkit.attached_header_addr(view) == 0\n"
            "del view\n"
        )

    def test_03_attached_view_of_attached_owner(self) -> None:
        """An attached view over an attached owner husks BOTH wrappers when
        the owner frees."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPAttachedBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = CCPAttachedBuffer(8)\n"
            "owner.values = b'01234567'\n"
            "view = CCPDualInterfaceTestToolkit.attached_c_from_header(CCPDualInterfaceTestToolkit.attached_header_addr(owner), False)\n"
            "assert view.values == b'01234567'\n"
            "owner.free_owned()\n"
            "assert owner.address == 'NULL'\n"
            "assert owner.size == 0\n"
            "assert view.address == 'NULL'\n"
            "assert view.size == 0\n"
            "assert CCPDualInterfaceTestToolkit.attached_header_addr(view) == 0\n"
            "del view\n"
        )

    def test_04_attached_embedded_lifecycle(self) -> None:
        """An attached embedded entry (interior pointer, attach_embedded)
        measures the remaining tail; writes land in the owner; freeing the
        owner husks the entry."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPAttachedBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = CCPAttachedBuffer(16)\n"
            "owner.values = b'0123456789'\n"
            "entry = CCPDualInterfaceTestToolkit.attached_embedded_from(owner, 3)\n"
            "assert CCPDualInterfaceTestToolkit.attached_header_addr(entry) == CCPDualInterfaceTestToolkit.attached_header_addr(owner) + 3\n"
            "assert int(entry.address, 16) == CCPDualInterfaceTestToolkit.attached_header_addr(entry)\n"
            "assert entry.values == b'3456789'\n"
            "entry.values = b'xyz'\n"
            "assert owner.values == b'012xyz' + b'\\x00' * 10\n"
            "owner.free_owned()\n"
            "assert entry.address == 'NULL'\n"
            "assert entry.size == 0\n"
            "assert CCPDualInterfaceTestToolkit.attached_header_addr(entry) == 0\n"
            "del entry\n"
        )

    def test_05_attached_embedded_adoption_helper(self) -> None:
        """attached_c_from_header_embedded adopts an interior pointer and
        attaches embedded inside — no caller-side attach; writes land in
        the owner."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPAttachedBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = CCPAttachedBuffer(8)\n"
            "owner.values = b'01234567'\n"
            "entry = CCPDualInterfaceTestToolkit.attached_c_from_header_embedded(CCPDualInterfaceTestToolkit.attached_header_addr(owner) + 3, CCPDualInterfaceTestToolkit.attached_header_addr(owner))\n"
            "assert entry.values == b'34567'\n"
            "entry.values = b'zz'\n"
            "assert owner.values == b'012zz' + b'\\x00' * 3\n"
            "owner.free_owned()\n"
            "assert CCPDualInterfaceTestToolkit.attached_header_addr(entry) == 0\n"
            "del entry\n"
        )

    def test_06_attached_child_husked_by_parent_free(self) -> None:
        """free_owned on the parent recursively frees the attached child:
        the child wrapper is husked while still alive."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPAttachedBuffer, CCPDualInterfaceTestToolkit\n"
            "parent = CCPAttachedBuffer(16)\n"
            "child = parent.alloc_child(8)\n"
            "assert child.address != 'NULL'\n"
            "child.values = b'child!!!'\n"
            "assert parent.values == b'\\x00' * 16\n"
            "parent.free_owned()\n"
            "assert child.address == 'NULL'\n"
            "assert child.size == 0\n"
            "assert CCPDualInterfaceTestToolkit.attached_header_addr(child) == 0\n"
            "del child\n"
        )

    def test_07_manual_detach_releases_binding_only(self) -> None:
        """attached_ccp_detach releases the binding (address 'NULL') but leaves
        the header intact; the owner then frees cleanly and the detached
        wrapper GCs silently."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import BoundBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = BoundBuffer(8)\n"
            "owner.values = b'01234567'\n"
            "view = CCPDualInterfaceTestToolkit.attached_c_from_header(CCPDualInterfaceTestToolkit.buffer_header_addr(owner), False)\n"
            "assert view.address != 'NULL'\n"
            "CCPDualInterfaceTestToolkit.attached_ccp_detach(view)\n"
            "assert view.address == 'NULL'\n"
            "assert CCPDualInterfaceTestToolkit.attached_header_addr(view) == CCPDualInterfaceTestToolkit.buffer_header_addr(owner)\n"
            "owner.free_owned()\n"
            "del view\n"
        )

    def test_08_unattached_wrappers_dealloc_gracefully(self) -> None:
        """A __new__-only wrapper (never attached) deallocates silently,
        and the owner free completes."""
        self._assert_clean_run(
            "import gc\n"
            "from cbase.allocator_protocol.c_dual_interface import BoundBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = BoundBuffer(8)\n"
            "owner.values = b'01234567'\n"
            "null_view = CCPDualInterfaceTestToolkit.attached_new_unbound()\n"
            "assert null_view.values is None\n"
            "assert null_view.address == 'NULL'\n"
            "del null_view\n"
            "gc.collect()\n"
            "owner.free_owned()\n"
        )

    def test_09_null_header_attach_raises(self) -> None:
        """Attaching an unbound (header-NULL) wrapper raises BufferError
        (error-proof construction path)."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPDualInterfaceTestToolkit\n"
            "null_view = CCPDualInterfaceTestToolkit.attached_new_unbound()\n"
            "assert null_view.values is None\n"
            "try:\n"
            "    CCPDualInterfaceTestToolkit.attached_ccp_attach(null_view)\n"
            "    raise AssertionError('expected BufferError')\n"
            "except BufferError:\n"
            "    pass\n"
            "del null_view\n"
        )

    def test_10_many_attach_free_cycles(self) -> None:
        """Repeated attach/free cycles stay stable (no freelist or
        callback-list corruption across iterations)."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPAttachedBuffer\n"
            "for i in range(100):\n"
            "    array = CCPAttachedBuffer(8)\n"
            "    array.values = b'abcdefgh'\n"
            "    array.free_owned()\n"
        )

    def test_11_bound_and_attached_coexist(self) -> None:
        """A bound (ccp_bind) and an attached (ccp_attach) wrapper over the
        same block are both husked when the owner frees."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPBoundBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = CCPBoundBuffer(8)\n"
            "owner.values = b'01234567'\n"
            "bound_view = CCPDualInterfaceTestToolkit.c_from_header(CCPDualInterfaceTestToolkit.header_addr(owner), False)\n"
            "attached_view = CCPDualInterfaceTestToolkit.attached_c_from_header(CCPDualInterfaceTestToolkit.header_addr(owner), False)\n"
            "assert bound_view.address != 'NULL'\n"
            "assert attached_view.address != 'NULL'\n"
            "owner.self_dealloc()\n"
            "assert bound_view.address == 'NULL'\n"
            "assert attached_view.address == 'NULL'\n"
            "assert CCPDualInterfaceTestToolkit.header_addr(bound_view) == 0\n"
            "assert CCPDualInterfaceTestToolkit.attached_header_addr(attached_view) == 0\n"
            "del bound_view\n"
            "del attached_view\n"
        )

    def test_12_gccp_attached_owner_graceful(self) -> None:
        """Garbage-collecting an attached owning wrapper frees the buffer
        without a vigilant abort or dealloc exceptions."""
        self._assert_clean_run(
            "import gc\n"
            "from cbase.allocator_protocol.c_dual_interface import CCPAttachedBuffer\n"
            "array = CCPAttachedBuffer(8)\n"
            "array.values = b'12345678'\n"
            "del array\n"
            "gc.collect()\n"
        )

    def test_13_gccp_attached_view_detaches_before_owner_free(self) -> None:
        """GC of an attached VIEW detaches via CCPAttachedBuffer.__dealloc__:
        the binding is released so the owner frees cleanly afterwards."""
        self._assert_clean_run(
            "import gc\n"
            "from cbase.allocator_protocol.c_dual_interface import CCPAttachedBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = CCPAttachedBuffer(8)\n"
            "view = CCPDualInterfaceTestToolkit.attached_c_from_header(CCPDualInterfaceTestToolkit.attached_header_addr(owner), False)\n"
            "del view\n"
            "gc.collect()\n"
            "owner.free_owned()\n"
        )

    def test_14_plain_buffer_owner_lifecycle(self) -> None:
        """A plain BoundBuffer round-trips values, allocates an owned child
        that frees itself on GC, and free_owned nulls the header (no FREE
        pass for unbound wrappers)."""
        self._assert_clean_run(
            "import gc\n"
            "from cbase.allocator_protocol.c_dual_interface import BoundBuffer, CCPDualInterfaceTestToolkit\n"
            "buf = BoundBuffer(16)\n"
            "buf.values = b'hello'\n"
            "assert buf.values == b'hello' + b'\\x00' * 11\n"
            "child = buf.alloc_child(4)\n"
            "child.values = b'abcd'\n"
            "assert child.values == b'abcd'\n"
            "del child\n"
            "gc.collect()\n"
            "buf.free_owned()\n"
            "assert CCPDualInterfaceTestToolkit.buffer_header_addr(buf) == 0\n"
            "assert buf.values is None\n"
            "del buf\n"
        )

    def test_15_plain_view_is_a_raw_pointer(self) -> None:
        """A plain view is a raw pointer: the owner free does NOT null its
        header (documented BoundBuffer semantics — no reverse invalidation);
        the non-owning view GCs without touching the buffer."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import BoundBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = BoundBuffer(8)\n"
            "owner.values = b'01234567'\n"
            "view = CCPDualInterfaceTestToolkit.buffer_c_from_header(CCPDualInterfaceTestToolkit.buffer_header_addr(owner), False)\n"
            "assert view.values == b'01234567'\n"
            "view.values = b'abcdefgh'\n"
            "assert owner.values == b'abcdefgh'\n"
            "view_addr = CCPDualInterfaceTestToolkit.buffer_header_addr(view)\n"
            "owner.free_owned()\n"
            "assert CCPDualInterfaceTestToolkit.buffer_header_addr(view) == view_addr\n"
            "del view\n"
        )

    def test_16_bound_embedded_adoption_helper(self) -> None:
        """c_from_header_embedded adopts an interior pointer and binds
        embedded inside; writes land in the parent, and the owner free
        husks the entry."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPBoundBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = CCPBoundBuffer(8)\n"
            "owner.values = b'01234567'\n"
            "entry = CCPDualInterfaceTestToolkit.c_from_header_embedded(CCPDualInterfaceTestToolkit.header_addr(owner) + 3, CCPDualInterfaceTestToolkit.header_addr(owner))\n"
            "assert CCPDualInterfaceTestToolkit.header_addr(entry) == CCPDualInterfaceTestToolkit.header_addr(owner) + 3\n"
            "assert int(entry.address, 16) == CCPDualInterfaceTestToolkit.header_addr(entry)\n"
            "assert entry.values == b'34567'\n"
            "entry.values = b'zz'\n"
            "assert owner.values == b'012zz' + b'\\x00' * 3\n"
            "owner.self_dealloc()\n"
            "assert CCPDualInterfaceTestToolkit.header_addr(entry) == 0\n"
            "del entry\n"
        )

    def test_17_attached_embedded_adoption_helper(self) -> None:
        """attached_c_from_header_embedded adopts an interior pointer and
        attaches embedded inside; the owner free husks the entry."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPAttachedBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = CCPAttachedBuffer(8)\n"
            "owner.values = b'01234567'\n"
            "entry = CCPDualInterfaceTestToolkit.attached_c_from_header_embedded(CCPDualInterfaceTestToolkit.attached_header_addr(owner) + 3, CCPDualInterfaceTestToolkit.attached_header_addr(owner))\n"
            "assert CCPDualInterfaceTestToolkit.attached_header_addr(entry) == CCPDualInterfaceTestToolkit.attached_header_addr(owner) + 3\n"
            "assert int(entry.address, 16) == CCPDualInterfaceTestToolkit.attached_header_addr(entry)\n"
            "assert entry.values == b'34567'\n"
            "entry.values = b'zz'\n"
            "assert owner.values == b'012zz' + b'\\x00' * 3\n"
            "owner.free_owned()\n"
            "assert CCPDualInterfaceTestToolkit.attached_header_addr(entry) == 0\n"
            "del entry\n"
        )

    def _assert_abort_run(self, code: str) -> None:
        proc = self._run_in_subprocess(code)
        self.assertEqual(proc.returncode, -6, f"stderr:\n{proc.stderr}")
        self.assertIn("[CCP] ERROR", proc.stderr)
        self.assertIn("double", proc.stderr)

    def test_18_double_attach_on_owned_aborts(self) -> None:
        """A second attach on an already-attached wrapper aborts (SIGABRT)
        with a [CCP] ERROR message on stderr — the ctx must be fresh (the
        zeroed allocation guarantees ap_header == NULL on first attach)."""
        self._assert_abort_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPAttachedBuffer, CCPDualInterfaceTestToolkit\n"
            "array = CCPAttachedBuffer(8)\n"
            "CCPDualInterfaceTestToolkit.attached_ccp_attach(array)\n"
        )

    def test_19_double_attach_after_adoption_aborts(self) -> None:
        """attached_c_from_header already attaches inside — an explicit
        attached_ccp_attach afterwards is a double attach and aborts."""
        self._assert_abort_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPAttachedBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = CCPAttachedBuffer(8)\n"
            "view = CCPDualInterfaceTestToolkit.attached_c_from_header(CCPDualInterfaceTestToolkit.attached_header_addr(owner), False)\n"
            "CCPDualInterfaceTestToolkit.attached_ccp_attach(view)\n"
        )

    def test_20_double_attach_embedded_aborts(self) -> None:
        """attached_c_from_header_embedded already attaches embedded inside
        — an explicit attached_ccp_attach_embedded afterwards aborts."""
        self._assert_abort_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPAttachedBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = CCPAttachedBuffer(8)\n"
            "entry = CCPDualInterfaceTestToolkit.attached_c_from_header_embedded(CCPDualInterfaceTestToolkit.attached_header_addr(owner) + 1, CCPDualInterfaceTestToolkit.attached_header_addr(owner))\n"
            "CCPDualInterfaceTestToolkit.attached_ccp_attach_embedded(entry, CCPDualInterfaceTestToolkit.attached_header_addr(owner))\n"
        )


class TestCCPAttachedAddressContract(unittest.TestCase):
    """Contract: ``CCPAttachedBuffer.address`` reports the wrapper's OWN
    bound C header — read from the header field slot at
    ``(char*)<PyObject*>self + ccp_ctx.ccp_header_offset``, the same slot
    the FREE pass nulls — NOT the attached protocol's buffer. The two
    coincide for a block-start attach and DIFFER for an embedded attach,
    where the protocol belongs to the PARENT block while the header is an
    interior pointer.

    Expected behavior:
        - owned / block-start view / child block: address == the wrapper's
          header address;
        - embedded: address == parent block start + index, and != the
          parent's own address (regression guard: the property used to
          report the parent's block);
        - manual detach reports 'NULL' while the header stays intact;
        - husked and never-attached wrappers report 'NULL', reads give
          None and writes raise BufferError.

    Oracle: the toolkit's attached_header_addr() is the C-side ground
    truth of the header field; address is parsed back from its hex string.
    """

    def test_00_owned_and_view_report_the_block_start(self) -> None:
        """An owned wrapper and a block-start view report the block start."""
        owner = CCPAttachedBuffer(16)
        view = TK.attached_c_from_header(TK.attached_header_addr(owner), False)

        self.assertEqual(int(owner.address, 16), TK.attached_header_addr(owner))
        self.assertEqual(int(view.address, 16), TK.attached_header_addr(view))
        self.assertEqual(TK.attached_header_addr(view), TK.attached_header_addr(owner))

    def test_01_embedded_reports_the_interior_pointer(self) -> None:
        """An embedded wrapper reports its own interior pointer — not the
        parent block its attachment protocol belongs to."""
        owner = CCPAttachedBuffer(16)
        entry = TK.attached_embedded_from(owner, 3)
        owner_addr = TK.attached_header_addr(owner)

        self.assertEqual(TK.attached_header_addr(entry), owner_addr + 3)
        self.assertEqual(int(entry.address, 16), TK.attached_header_addr(entry))
        self.assertNotEqual(int(entry.address, 16), owner_addr)

    def test_02_child_block_reports_its_own_start(self) -> None:
        """A child block reports its own start, not its parent's."""
        parent = CCPAttachedBuffer(64)
        child = parent.alloc_child(16)

        self.assertEqual(int(child.address, 16), TK.attached_header_addr(child))
        self.assertNotEqual(TK.attached_header_addr(child), TK.attached_header_addr(parent))

    def test_03_husk_and_never_attached_report_null(self) -> None:
        """Husked wrappers (owner freed) and never-attached wrappers report
        'NULL'."""
        owner = CCPAttachedBuffer(16)
        view = TK.attached_c_from_header(TK.attached_header_addr(owner), False)
        entry = TK.attached_embedded_from(owner, 3)
        never_attached = TK.attached_new_unbound()

        owner.free_owned()

        for wrapper in (owner, view, entry, never_attached):
            self.assertEqual(wrapper.address, 'NULL')

    def test_04_manual_detach_nulls_address_keeps_header(self) -> None:
        """A manual detach releases the binding only: address reports
        'NULL' while the header field itself stays intact."""
        owner = CCPAttachedBuffer(16)
        view = TK.attached_c_from_header(TK.attached_header_addr(owner), False)
        view_addr = TK.attached_header_addr(view)

        TK.attached_ccp_detach(view)

        self.assertEqual(view.address, 'NULL')
        with self.assertRaises(BufferError):
            view.embedded
        self.assertEqual(TK.attached_header_addr(view), view_addr)

    def test_05_husk_reads_none_and_rejects_writes(self) -> None:
        """A husked attached wrapper reads None and refuses writes."""
        owner = CCPAttachedBuffer(16)
        entry = TK.attached_embedded_from(owner, 2)

        owner.free_owned()

        self.assertIsNone(entry.values)
        with self.assertRaises(BufferError):
            entry.values = b'ab'

    def test_06_embedded_flag_distinguishes_interior_headers(self) -> None:
        """The embedded flag marks interior-pointer attaches: False for
        every block-start role (owned, view, child), True for an embedded
        entry — and BufferError once detached (husked or never attached)."""
        owner = CCPAttachedBuffer(64)
        view = TK.attached_c_from_header(TK.attached_header_addr(owner), False)
        child = owner.alloc_child(16)
        entry = TK.attached_embedded_from(owner, 3)

        self.assertFalse(owner.embedded)
        self.assertFalse(view.embedded)
        self.assertFalse(child.embedded)
        self.assertTrue(entry.embedded)

        owner.free_owned()

        for wrapper in (owner, view, entry, child, TK.attached_new_unbound()):
            with self.assertRaises(BufferError):
                wrapper.embedded


if __name__ == '__main__':
    unittest.main()
