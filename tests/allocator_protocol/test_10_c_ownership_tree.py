import subprocess
import sys
import unittest

from cbase.allocator_protocol.c_dual_interface import (
    CCPBoundBuffer,
    CCPDualInterfaceTestToolkit,
)

TK = CCPDualInterfaceTestToolkit


class TestOwnershipTreeStructure(unittest.TestCase):
    """Contract: c_ap_alloc_child links a new block into the parent's
    doubly-linked child list (push-front), c_ap_free_owned recursively frees
    the subtree, and c_ap_free unlinks a child from its parent's list.

    Expected behavior:
        - Every child's parent pointer equals the parent block; sibling
          pointers form a consistent doubly-linked list whose head is the
          most recently allocated child.
        - free_owned on a child frees only its subtree and re-links the
          parent's list; free_owned on the parent husks every descendant
          wrapper (header NULL, size 0).
        - Operations on a released buffer raise BufferError or no-op.

    Oracle: protocol_addr()/hierarchy_addr() report the raw C pointers;
    sibling links are cross-checked pairwise (a.next == b implies
    b.prev == a).
    """

    @staticmethod
    def _hierarchy(array: CCPBoundBuffer) -> tuple[int, int, int, int]:
        return TK.hierarchy_addr(array)

    def test_00_alloc_child_links_parent(self) -> None:
        """A single child points at its parent; both child lists are empty."""
        parent = CCPBoundBuffer(1024)
        child = parent.alloc_child(64)

        p_parent, p_first_child, p_next, p_prev = self._hierarchy(parent)
        c_parent, c_first_child, c_next, c_prev = self._hierarchy(child)

        self.assertEqual(p_parent, 0)
        self.assertEqual(p_first_child, TK.protocol_addr(child))
        self.assertEqual(p_next, 0)
        self.assertEqual(p_prev, 0)
        self.assertEqual(c_parent, TK.protocol_addr(parent))
        self.assertEqual(c_first_child, 0)
        self.assertEqual(c_next, 0)
        self.assertEqual(c_prev, 0)
        self.assertEqual(child.size, 64)

    def test_01_siblings_form_doubly_linked_list(self) -> None:
        """Three children form head = most recent: c3 -> c2 -> c1."""
        parent = CCPBoundBuffer(1024)
        c1 = parent.alloc_child(16)
        c2 = parent.alloc_child(16)
        c3 = parent.alloc_child(16)

        p_parent, p_first, _, _ = self._hierarchy(parent)
        self.assertEqual(p_first, TK.protocol_addr(c3))

        _, _, n3, p3 = self._hierarchy(c3)
        _, _, n2, p2 = self._hierarchy(c2)
        _, _, n1, p1 = self._hierarchy(c1)
        self.assertEqual(n3, TK.protocol_addr(c2))
        self.assertEqual(p3, 0)
        self.assertEqual(n2, TK.protocol_addr(c1))
        self.assertEqual(p2, TK.protocol_addr(c3))
        self.assertEqual(n1, 0)
        self.assertEqual(p1, TK.protocol_addr(c2))

    def test_02_grandchild_links_into_its_own_parent(self) -> None:
        """A grandchild is listed under its parent, not the root."""
        parent = CCPBoundBuffer(1024)
        child = parent.alloc_child(64)
        grandchild = child.alloc_child(32)

        g_parent, g_first, _, _ = self._hierarchy(grandchild)
        c_parent, c_first, _, _ = self._hierarchy(child)
        self.assertEqual(g_parent, TK.protocol_addr(child))
        self.assertEqual(g_first, 0)
        self.assertEqual(c_parent, TK.protocol_addr(parent))
        self.assertEqual(c_first, TK.protocol_addr(grandchild))

        p_parent, p_first, _, _ = self._hierarchy(parent)
        self.assertEqual(p_first, TK.protocol_addr(child))

    def test_03_free_owned_child_unlinks_from_parent_list(self) -> None:
        """free_owned on a middle child husks it and re-links the list."""
        parent = CCPBoundBuffer(1024)
        c1 = parent.alloc_child(16)
        c2 = parent.alloc_child(16)
        c3 = parent.alloc_child(16)  # head: c3 -> c2 -> c1

        c2.free_owned()

        self.assertEqual(TK.header_addr(c2), 0)
        self.assertEqual(c2.size, 0)

        p_parent, p_first, _, _ = self._hierarchy(parent)
        self.assertEqual(p_first, TK.protocol_addr(c3))
        _, _, n3, _ = self._hierarchy(c3)
        _, _, n1, p1 = self._hierarchy(c1)
        self.assertEqual(n3, TK.protocol_addr(c1))
        self.assertEqual(p1, TK.protocol_addr(c3))

        # Survivors remain usable.
        c1.values = b'ab'
        self.assertEqual(c1.values[:2], b'ab')

    def test_04_free_owned_parent_deep_frees_tree(self) -> None:
        """free_owned on the root husks every descendant wrapper."""
        parent = CCPBoundBuffer(1024)
        c1 = parent.alloc_child(16)
        c2 = parent.alloc_child(16)
        grandchild = c1.alloc_child(8)

        parent.free_owned()

        for wrapper in (parent, c1, c2, grandchild):
            self.assertEqual(TK.header_addr(wrapper), 0)
            self.assertEqual(wrapper.size, 0)

    def test_05_alloc_child_after_release_raises(self) -> None:
        """A released parent refuses to spawn children."""
        parent = CCPBoundBuffer(256)
        parent.free_owned()
        with self.assertRaises(BufferError):
            parent.alloc_child(8)

    def test_06_free_owned_idempotent_on_released_buffer(self) -> None:
        """free_owned on an already-released buffer is a no-op."""
        parent = CCPBoundBuffer(256)
        parent.free_owned()
        parent.free_owned()


class TestOwnershipTreeRealloc(unittest.TestCase):
    """Contract: c_ap_realloc grows a block by alloc-copy-free (the
    ownership tree migrates to the moved address) and shrinks in place
    (header size only — the block is not recycled).

    Expected behavior:
        - Growing a parent repoints every child's parent pointer at the
          new block and preserves the child content.
        - Growing a child re-links the parent's list and sibling links to
          the new block.
        - On grow the passed wrapper is husked and the returned wrapper
          owns the moved block; on shrink the SAME wrapper is returned
          with the updated size.

    Oracle: pointer identities via protocol_addr()/hierarchy_addr() before
    and after the move.
    """

    @staticmethod
    def _hierarchy(array: CCPBoundBuffer) -> tuple[int, int, int, int]:
        return TK.hierarchy_addr(array)

    def test_00_realloc_parent_migrates_children(self) -> None:
        """Children follow the moved parent; content is preserved."""
        parent = CCPBoundBuffer(1024)
        c1 = parent.alloc_child(16)
        c1.values = b'child-data'
        c2 = parent.alloc_child(32)
        old_parent_addr = TK.protocol_addr(parent)

        new_parent = TK.realloc_owned(parent, 2048)

        self.assertEqual(TK.header_addr(parent), 0)
        self.assertEqual(parent.size, 0)
        self.assertEqual(new_parent.size, 2048)
        self.assertNotEqual(TK.protocol_addr(new_parent), old_parent_addr)

        p_parent, p_first, _, _ = self._hierarchy(new_parent)
        self.assertEqual(p_parent, 0)
        self.assertEqual(p_first, TK.protocol_addr(c2))  # head order kept

        c1_parent, _, _, _ = self._hierarchy(c1)
        c2_parent, _, _, _ = self._hierarchy(c2)
        self.assertEqual(c1_parent, TK.protocol_addr(new_parent))
        self.assertEqual(c2_parent, TK.protocol_addr(new_parent))
        self.assertEqual(c1.values[:10], b'child-data')

    def test_01_realloc_child_relinks_sibling_list(self) -> None:
        """Reallocating the tail child re-links prev/next around it."""
        parent = CCPBoundBuffer(1024)
        c1 = parent.alloc_child(16)
        c2 = parent.alloc_child(16)  # head: c2 -> c1
        old_c1_addr = TK.protocol_addr(c1)

        new_c1 = TK.realloc_owned(c1, 256)

        self.assertEqual(TK.header_addr(c1), 0)
        self.assertNotEqual(TK.protocol_addr(new_c1), old_c1_addr)

        c1_parent, _, n1, p1 = self._hierarchy(new_c1)
        self.assertEqual(c1_parent, TK.protocol_addr(parent))
        self.assertEqual(n1, 0)
        self.assertEqual(p1, TK.protocol_addr(c2))

        _, _, n2, _ = self._hierarchy(c2)
        self.assertEqual(n2, TK.protocol_addr(new_c1))

        p_parent, p_first, _, _ = self._hierarchy(parent)
        self.assertEqual(p_first, TK.protocol_addr(c2))

    def test_02_realloc_shrink_updates_in_place(self) -> None:
        """Shrinking keeps the same block; only the header size changes."""
        parent = CCPBoundBuffer(256)
        parent.values = b'x' * 128
        old_addr = TK.header_addr(parent)

        same = TK.realloc_owned(parent, 64)

        self.assertIs(same, parent)
        self.assertEqual(TK.header_addr(parent), old_addr)
        self.assertEqual(parent.size, 64)
        self.assertEqual(parent.values[:64], b'x' * 64)


class TestOwnershipAcquire(unittest.TestCase):
    """Contract: c_ap_acquire_ownership detaches a block from its parent's
    child list — the block (with its own subtree) becomes an independent
    root; the refcount is untouched.

    Expected behavior:
        - Detaching a child re-links the parent's list around it and clears
          the child's tree links (parent/prev/next all NULL).
        - The detached subtree stays intact and survives the parent's
          free_owned; the detached block frees independently.
        - Detaching a root is an idempotent no-op.

    Oracle: pointer identities via protocol_addr()/hierarchy_addr() before
    and after the detach.
    """

    @staticmethod
    def _hierarchy(array: CCPBoundBuffer) -> tuple[int, int, int, int]:
        return TK.hierarchy_addr(array)

    def test_00_detach_tail_child(self) -> None:
        """Detaching the tail child re-links the head chain."""
        parent = CCPBoundBuffer(1024)
        c1 = parent.alloc_child(16)
        c2 = parent.alloc_child(16)  # head: c2 -> c1

        TK.acquire_ownership(c1)

        p_parent, p_first, _, _ = self._hierarchy(parent)
        self.assertEqual(p_first, TK.protocol_addr(c2))
        _, _, n2, _ = self._hierarchy(c2)
        self.assertEqual(n2, 0)
        c1_parent, _, c1_next, c1_prev = self._hierarchy(c1)
        self.assertEqual(c1_parent, 0)
        self.assertEqual(c1_next, 0)
        self.assertEqual(c1_prev, 0)

        parent.free_owned()
        self.assertEqual(TK.header_addr(c2), 0)
        self.assertNotEqual(TK.header_addr(c1), 0)  # detached child survives
        c1.values = b'z'
        self.assertEqual(c1.values[:1], b'z')
        c1.free_owned()
        self.assertEqual(TK.header_addr(c1), 0)

    def test_01_detach_head_child(self) -> None:
        """Detaching the head child empties the parent's list."""
        parent = CCPBoundBuffer(1024)
        c1 = parent.alloc_child(16)

        TK.acquire_ownership(c1)

        p_parent, p_first, _, _ = self._hierarchy(parent)
        self.assertEqual(p_first, 0)
        c1_parent, _, _, _ = self._hierarchy(c1)
        self.assertEqual(c1_parent, 0)

    def test_02_detach_keeps_subtree(self) -> None:
        """A detached child keeps its own children; the parent frees alone."""
        parent = CCPBoundBuffer(1024)
        c1 = parent.alloc_child(64)
        grandchild = c1.alloc_child(8)

        TK.acquire_ownership(c1)

        c1_parent, c1_first, _, _ = self._hierarchy(c1)
        self.assertEqual(c1_parent, 0)
        self.assertEqual(c1_first, TK.protocol_addr(grandchild))

        parent.free_owned()
        self.assertEqual(TK.header_addr(parent), 0)
        self.assertNotEqual(TK.header_addr(c1), 0)          # survivor
        self.assertNotEqual(TK.header_addr(grandchild), 0)  # survivor

        c1.free_owned()
        self.assertEqual(TK.header_addr(c1), 0)
        self.assertEqual(TK.header_addr(grandchild), 0)

    def test_03_detach_root_is_noop(self) -> None:
        """Detaching a root leaves it fully usable."""
        parent = CCPBoundBuffer(256)
        parent.values = b'root-data'

        TK.acquire_ownership(parent)

        p_parent, p_first, _, _ = self._hierarchy(parent)
        self.assertEqual(p_parent, 0)
        self.assertEqual(p_first, 0)
        self.assertEqual(parent.values[:9], b'root-data')

    def test_04_transfer_to_new_parent(self) -> None:
        """A child moves from one parent to another; the old list stays intact."""
        p1 = CCPBoundBuffer(1024)
        p2 = CCPBoundBuffer(1024)
        c = p1.alloc_child(16)

        TK.acquire_ownership(c, TK.header_addr(p2))

        c_parent, _, c_next, c_prev = self._hierarchy(c)
        self.assertEqual(c_parent, TK.protocol_addr(p2))
        self.assertEqual(c_next, 0)
        self.assertEqual(c_prev, 0)
        p1_parent, p1_first, _, _ = self._hierarchy(p1)
        self.assertEqual(p1_first, 0)
        p2_parent, p2_first, _, _ = self._hierarchy(p2)
        self.assertEqual(p2_first, TK.protocol_addr(c))

        p2.free_owned()
        self.assertEqual(TK.header_addr(c), 0)
        self.assertNotEqual(TK.header_addr(p1), 0)
        p1.free_owned()

    def test_05_transfer_reheads_under_same_parent(self) -> None:
        """Re-parenting under the same parent moves the block to the head."""
        p = CCPBoundBuffer(1024)
        c1 = p.alloc_child(16)
        c2 = p.alloc_child(16)  # head: c2 -> c1

        TK.acquire_ownership(c1, TK.header_addr(p))

        p_parent, p_first, _, _ = self._hierarchy(p)
        self.assertEqual(p_first, TK.protocol_addr(c1))
        _, _, n1, p1 = self._hierarchy(c1)
        _, _, n2, p2_prev = self._hierarchy(c2)
        self.assertEqual(n1, TK.protocol_addr(c2))
        self.assertEqual(p1, 0)
        self.assertEqual(n2, 0)
        self.assertEqual(p2_prev, TK.protocol_addr(c1))

    def test_06_transfer_moves_subtree(self) -> None:
        """The moved block keeps its own children under the new parent."""
        p1 = CCPBoundBuffer(1024)
        p2 = CCPBoundBuffer(1024)
        c1 = p1.alloc_child(64)
        grandchild = c1.alloc_child(8)

        TK.acquire_ownership(c1, TK.header_addr(p2))

        c1_parent, c1_first, _, _ = self._hierarchy(c1)
        self.assertEqual(c1_parent, TK.protocol_addr(p2))
        self.assertEqual(c1_first, TK.protocol_addr(grandchild))

        p2.free_owned()
        self.assertEqual(TK.header_addr(c1), 0)
        self.assertEqual(TK.header_addr(grandchild), 0)
        self.assertNotEqual(TK.header_addr(p1), 0)


class TestOwnershipTransferGuard(unittest.TestCase):
    """Contract: c_ap_acquire_ownership rejects cycles — a block cannot be
    parented under itself or its own descendant (VIGILANT abort).

    Oracle: the child process aborts (nonzero exit) and stderr carries the
    "[AP_ALLOC_VIGILANT] ERROR" marker plus the cycle message.
    """

    def test_00_transfer_to_own_descendant_aborts(self) -> None:
        code = (
            "from cbase.allocator_protocol.c_dual_interface import "
            "CCPBoundBuffer, CCPDualInterfaceTestToolkit\n"
            "p = CCPBoundBuffer(1024)\n"
            "c = p.alloc_child(16)\n"
            "CCPDualInterfaceTestToolkit.acquire_ownership("
            "p, CCPDualInterfaceTestToolkit.header_addr(c))\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("[AP_ALLOC_VIGILANT] ERROR", proc.stderr)
        self.assertIn("cannot parent a block under itself", proc.stderr)

    def test_01_transfer_to_self_aborts(self) -> None:
        code = (
            "from cbase.allocator_protocol.c_dual_interface import "
            "CCPBoundBuffer, CCPDualInterfaceTestToolkit\n"
            "p = CCPBoundBuffer(1024)\n"
            "CCPDualInterfaceTestToolkit.acquire_ownership("
            "p, CCPDualInterfaceTestToolkit.header_addr(p))\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("[AP_ALLOC_VIGILANT] ERROR", proc.stderr)
        self.assertIn("cannot parent a block under itself", proc.stderr)


class TestVigilantChildGuard(unittest.TestCase):
    """Contract: c_ap_free refuses to free a buffer that still owns
    children (VIGILANT abort), directing the caller to c_ap_free_owned.

    Oracle: the child process aborts (nonzero exit) and stderr carries the
    "[AP_ALLOC_VIGILANT] ERROR" marker plus the c_ap_free_owned hint.
    """

    def test_00_raw_free_on_parent_aborts(self) -> None:
        code = (
            "from cbase.allocator_protocol.c_dual_interface import "
            "CCPBoundBuffer, CCPDualInterfaceTestToolkit\n"
            "p = CCPBoundBuffer(1024)\n"
            "c = p.alloc_child(16)  # keep alive — dropping it would free it\n"
            "CCPDualInterfaceTestToolkit.raw_free(p)\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("[AP_ALLOC_VIGILANT] ERROR", proc.stderr)
        self.assertIn("c_ap_free_owned", proc.stderr)


if __name__ == "__main__":
    unittest.main()
