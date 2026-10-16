# -*- coding: utf-8 -*-
# GUILD → SQUAD → MATCH BRIDGE
# - Guild join ke baad turant squad banao
# - Har squad match ke baad naya squad banao (fast rotation)
import asyncio, time
from typing import Dict, List, Set

# ═══════════════════════════════════════════════════════════════
# SQUAD POOL STATE (per-squad, race-free)
# ═══════════════════════════════════════════════════════════════
_squads: Dict[int, Dict] = {}
_squads_lock = asyncio.Lock()
_peer_to_squad: Dict[str, int] = {}
_free_accounts: Set[str] = set()  # UIDs ready for new squad


def _new_squad_state(squad_id: int, expected_size: int = 4):
    return {
        "id": squad_id,
        "peers": {},
        "leader_uid": None,
        "team_code": None,
        "pk_code": None,
        "members": set(),
        "members_lock": asyncio.Lock(),
        "lock": asyncio.Lock(),
        "expected": expected_size,
        "created_at": time.time(),
        "match_done": False,
        "ready_event": asyncio.Event(),
    }


async def get_or_create_squad_for(uid: str) -> Dict:
    """Assign uid to a squad (round-robin, race-free)."""
    uid = str(uid)
    async with _squads_lock:
        # Already assigned to an active squad?
        sid = _peer_to_squad.get(uid)
        if sid is not None and sid in _squads:
            sq = _squads[sid]
            if not sq["match_done"]:
                return sq

        # Find an open squad with space
        for sid, sq in sorted(_squads.items()):
            if sq["match_done"]:
                continue
            if len(sq["peers"]) < sq["expected"]:
                _peer_to_squad[uid] = sid
                return sq

        # Create new squad
        new_id = (max(_squads.keys()) + 1) if _squads else 1
        sq = _new_squad_state(new_id)
        _squads[new_id] = sq
        _peer_to_squad[uid] = new_id
        print(f"[SQUAD #{new_id}] 🆕 created — waiting for {sq['expected']} peers", flush=True)
        return sq


async def register_peer(squad: Dict, uid: str, writer, account_data, key, iv):
    """Register this peer into its squad."""
    uid = str(uid)
    async with squad["lock"]:
        squad["peers"][uid] = {
            "writer": writer,
            "data": account_data,
            "key": key,
            "iv": iv,
            "joined_at": time.time(),
        }
        if squad["leader_uid"] is None:
            squad["leader_uid"] = uid
            print(f"[SQUAD #{squad['id']}] 👑 {uid} is leader", flush=True)


async def unregister_peer(squad: Dict, uid: str):
    """Remove peer from squad. If empty → mark done + cleanup."""
    uid = str(uid)
    async with squad["lock"]:
        squad["peers"].pop(uid, None)
        if squad["leader_uid"] == uid:
            squad["leader_uid"] = None
        if len(squad["peers"]) == 0:
            squad["match_done"] = True
            print(f"[SQUAD #{squad['id']}] ✅ all peers left — marking done", flush=True)
        # reset members
        async with squad["members_lock"]:
            squad["members"].discard(uid)


async def cleanup_squad(squad_id: int):
    """Remove squad + free its UIDs."""
    async with _squads_lock:
        sq = _squads.get(squad_id)
        if not sq:
            return
        if sq["match_done"] and len(sq["peers"]) == 0:
            for uid in list(_peer_to_squad.keys()):
                if _peer_to_squad[uid] == squad_id:
                    del _peer_to_squad[uid]
                    _free_accounts.add(uid)
            del _squads[squad_id]
            print(f"[SQUAD #{squad_id}] 🧹 cleaned up — {len(_free_accounts)} accounts freed", flush=True)


async def get_squad_stats() -> Dict:
    async with _squads_lock:
        active = sum(1 for s in _squads.values() if not s["match_done"])
        total = len(_squads)
        return {
            "active_squads": active,
            "total_squads": total,
            "squad_ids": list(_squads.keys()),
            "free_accounts": list(_free_accounts),
        }


async def wait_squad_full(squad: Dict, timeout: float = 60.0):
    """Wait until squad has expected number of peers."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        async with squad["lock"]:
            if len(squad["peers"]) >= squad["expected"]:
                return True
            if squad["match_done"]:
                return False
        await asyncio.sleep(0.5)
    return False


async def mark_member_joined(squad: Dict, uid: str):
    """Mark a member as joined the squad."""
    async with squad["members_lock"]:
        squad["members"].add(str(uid))
        n = len(squad["members"])
    print(f"[SQUAD #{squad['id']}] 👥 {n}/{squad['expected']} — joined {uid}", flush=True)
    if n >= squad["expected"]:
        squad["ready_event"].set()
        print(f"[SQUAD #{squad['id']}] 🎉 FULL — all {n} members ready", flush=True)


async def member_leave(squad: Dict, uid: str):
    async with squad["members_lock"]:
        squad["members"].discard(str(uid))


async def member_count(squad: Dict) -> int:
    async with squad["members_lock"]:
        return len(squad["members"])


async def wait_squad_members(squad: Dict, timeout: float = 90.0) -> bool:
    try:
        await asyncio.wait_for(squad["ready_event"].wait(), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        return False