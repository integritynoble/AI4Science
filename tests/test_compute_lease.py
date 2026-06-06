"""Concurrency lease: each compute provider serves at most max_concurrent users."""
import time

from ai4science.compute.lease import (
    acquire_lease, release_lease, active_leases, available_slots,
)
from ai4science.compute.registry import ComputeProvider


def _provider(tmp_path, max_concurrent=2):
    return ComputeProvider(
        provider_id="main-cpu",
        wallet_address="0xde81b29E42F95C92c9A4Dc78882d0F05D2C81A29",
        endpoint_path=str(tmp_path / "inbox"),
        kind="cpu",
        max_concurrent=max_concurrent,
    )


def test_acquire_up_to_max_then_full(tmp_path):
    prov = _provider(tmp_path, max_concurrent=2)
    assert available_slots(prov) == 2

    l1 = acquire_lease(prov, holder="userA")
    l2 = acquire_lease(prov, holder="userB")
    assert l1 is not None and l2 is not None
    assert l1.slot != l2.slot                      # distinct slots
    assert available_slots(prov) == 0

    # third user is refused — server full
    l3 = acquire_lease(prov, holder="userC")
    assert l3 is None
    assert len(active_leases(prov)) == 2


def test_release_frees_a_slot(tmp_path):
    prov = _provider(tmp_path, max_concurrent=2)
    l1 = acquire_lease(prov, holder="userA")
    acquire_lease(prov, holder="userB")
    assert acquire_lease(prov, holder="userC") is None   # full

    assert release_lease(prov, l1) is True
    assert available_slots(prov) == 1
    l3 = acquire_lease(prov, holder="userC")             # now fits
    assert l3 is not None


def test_expired_lease_is_reclaimed(tmp_path):
    prov = _provider(tmp_path, max_concurrent=1)
    acquire_lease(prov, holder="stale", ttl_s=1)
    assert acquire_lease(prov, holder="fresh") is None   # full (not yet expired)
    time.sleep(1.2)
    # the stale lease has expired → a new holder can reclaim the single slot
    assert active_leases(prov) == []
    assert acquire_lease(prov, holder="fresh") is not None


def test_release_wrong_holder_is_noop(tmp_path):
    prov = _provider(tmp_path, max_concurrent=2)
    l1 = acquire_lease(prov, holder="userA")
    # forging a lease for someone else's slot must not release it
    l1_forged = l1.model_copy(update={"holder": "attacker"})
    assert release_lease(prov, l1_forged) is False
    assert available_slots(prov) == 1                    # still held by userA
