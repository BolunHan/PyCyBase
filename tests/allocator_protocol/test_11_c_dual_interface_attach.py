import subprocess
import sys
import unittest


class TestCCPAttachmentProtocol(unittest.TestCase):
    """Contract: the CCP attachment protocol binds a wrapper through an
    embedded ccp_ctx VALUE field (no CCPType inheritance, no ccp_protocol
    cast) — usable by classes that cannot inherit CCPType.

    - BoundBuffer is the plain c-dual-interface design: owner flag only, no
      reverse dealloc invalidation (views are raw pointers).
    - CCPAttachedBuffer(BoundBuffer) embeds ``cdef ccp_ctx ccp_ctx`` and
      registers every init/adoption via c_attach / c_attach_embedded; the
      FREE pass detaches the wrapper, runs the armed __ccp_dealloc__ hook
      (zeroes size), and nulls the header.
    - CCPType itself stays bound-only (ccp_bind family).

    Expected behavior:
        - attached owned buffers round-trip values and free gracefully;
          every attached wrapper of the block is husked on the owner free.
        - the attachment works across a plain (unbound) owner, an attached
          owner, interior pointers (attach_embedded), and child blocks.
        - manual detach releases only the binding (header stays intact);
          unattached and NULL-header wrappers dealloc / raise gracefully.
        - bound and attached wrappers coexist on the same block.

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
            "CCPDualInterfaceTestToolkit.attached_attach(view)\n"
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
            "CCPDualInterfaceTestToolkit.attached_attach(view)\n"
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
            "assert entry.values == b'3456789'\n"
            "entry.values = b'xyz'\n"
            "assert owner.values == b'012xyz' + b'\\x00' * 10\n"
            "owner.free_owned()\n"
            "assert entry.address == 'NULL'\n"
            "assert entry.size == 0\n"
            "assert CCPDualInterfaceTestToolkit.attached_header_addr(entry) == 0\n"
            "del entry\n"
        )

    def test_05_attached_two_step_embedded(self) -> None:
        """The explicit two-step path — c_from_header on an interior pointer
        then attached_attach_embedded with the parent block address —
        works."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPAttachedBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = CCPAttachedBuffer(8)\n"
            "owner.values = b'01234567'\n"
            "entry = CCPDualInterfaceTestToolkit.attached_c_from_header(CCPDualInterfaceTestToolkit.attached_header_addr(owner) + 3, False)\n"
            "CCPDualInterfaceTestToolkit.attached_attach_embedded(entry, CCPDualInterfaceTestToolkit.attached_header_addr(owner))\n"
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
        """attached_detach releases the binding (address 'NULL') but leaves
        the header intact; the owner then frees cleanly and the detached
        wrapper GCs silently."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import BoundBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = BoundBuffer(8)\n"
            "owner.values = b'01234567'\n"
            "view = CCPDualInterfaceTestToolkit.attached_c_from_header(CCPDualInterfaceTestToolkit.buffer_header_addr(owner), False)\n"
            "CCPDualInterfaceTestToolkit.attached_attach(view)\n"
            "assert view.address != 'NULL'\n"
            "CCPDualInterfaceTestToolkit.attached_detach(view)\n"
            "assert view.address == 'NULL'\n"
            "assert CCPDualInterfaceTestToolkit.attached_header_addr(view) == CCPDualInterfaceTestToolkit.buffer_header_addr(owner)\n"
            "owner.free_owned()\n"
            "del view\n"
        )

    def test_08_unattached_wrappers_dealloc_gracefully(self) -> None:
        """Wrappers created WITHOUT ccp_attach must still deallocate
        silently: an unattached view over a live owner, a NULL-header
        wrapper, and the owner free."""
        self._assert_clean_run(
            "import gc\n"
            "from cbase.allocator_protocol.c_dual_interface import BoundBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = BoundBuffer(8)\n"
            "owner.values = b'01234567'\n"
            "view = CCPDualInterfaceTestToolkit.attached_c_from_header(CCPDualInterfaceTestToolkit.buffer_header_addr(owner), False)\n"
            "assert view.values == b'01234567'\n"
            "assert view.address == 'NULL'\n"
            "del view\n"
            "gc.collect()\n"
            "null_view = CCPDualInterfaceTestToolkit.attached_c_from_header(0, False)\n"
            "assert null_view.values is None\n"
            "del null_view\n"
            "gc.collect()\n"
            "owner.free_owned()\n"
        )

    def test_09_null_header_attach_raises(self) -> None:
        """Attaching a NULL-header wrapper raises BufferError (error-proof
        construction path)."""
        self._assert_clean_run(
            "from cbase.allocator_protocol.c_dual_interface import CCPDualInterfaceTestToolkit\n"
            "null_view = CCPDualInterfaceTestToolkit.attached_c_from_header(0, False)\n"
            "assert null_view.values is None\n"
            "try:\n"
            "    CCPDualInterfaceTestToolkit.attached_attach(null_view)\n"
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
            "CCPDualInterfaceTestToolkit.ccp_bind(bound_view)\n"
            "attached_view = CCPDualInterfaceTestToolkit.attached_c_from_header(CCPDualInterfaceTestToolkit.header_addr(owner), False)\n"
            "CCPDualInterfaceTestToolkit.attached_attach(attached_view)\n"
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

    def test_12_gc_attached_owner_graceful(self) -> None:
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

    def test_13_gc_attached_view_detaches_before_owner_free(self) -> None:
        """GC of an attached VIEW detaches via CCPAttachedBuffer.__dealloc__:
        the binding is released so the owner frees cleanly afterwards."""
        self._assert_clean_run(
            "import gc\n"
            "from cbase.allocator_protocol.c_dual_interface import CCPAttachedBuffer, CCPDualInterfaceTestToolkit\n"
            "owner = CCPAttachedBuffer(8)\n"
            "view = CCPDualInterfaceTestToolkit.attached_c_from_header(CCPDualInterfaceTestToolkit.attached_header_addr(owner), False)\n"
            "CCPDualInterfaceTestToolkit.attached_attach(view)\n"
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


if __name__ == '__main__':
    unittest.main()
