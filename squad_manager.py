# -*- coding: utf-8 -*-
# SQUAD MANAGER — Per-guild squads
import asyncio, time
from typing import Dict, List, Optional, Any


class Squad:
    def __init__(self, squad_id: int, guild_id: str, size: int = 4):
        self.id = squad_id
        self.guild_id = str(guild_id)
        self.size = size
        self.members: Dict[str, Dict] = {}
        self.leader_uid: Optional[str] = None
        self.lock = asyncio.Lock()
        self.full_event = asyncio.Event()
        self.in_match = False
        self.match_count = 0
        self.created_at = time.time()

    def is_full(self) -> bool:
        return len(self.members) >= self.size


class SquadManager:
    def __init__(self, squad_size: int = 4):
        self.squad_size = squad_size
        # guild_id -> list of squads
        self.squads_by_guild: Dict[str, List[Squad]] = {}
        self.uid_to_squad: Dict[str, Squad] = {}
        self.next_squad_id = 1
        self.lock = asyncio.Lock()
        self.ready_accounts: set = set()

    async def mark_ready(self, uid: str):
        async with self.lock:
            self.ready_accounts.add(str(uid))

    async def mark_not_ready(self, uid: str):
        async with self.lock:
            self.ready_accounts.discard(str(uid))

    def is_ready(self, uid: str) -> bool:
        return str(uid) in self.ready_accounts

    async def get_or_create_squad(self, uid: str, guild_id: str = "default") -> Squad:
        """Har guild ke liye alag squad pool."""
        uid = str(uid)
        guild_id = str(guild_id)
        async with self.lock:
            # Already assigned?
            if uid in self.uid_to_squad:
                sq = self.uid_to_squad[uid]
                if not sq.is_full() or uid in sq.members:
                    return sq

            # Find non-full squad in this guild
            guild_squads = self.squads_by_guild.setdefault(guild_id, [])
            for sq in guild_squads:
                if not sq.is_full():
                    self.uid_to_squad[uid] = sq
                    return sq

            # Create new squad for this guild
            new_squad = Squad(self.next_squad_id, guild_id, self.squad_size)
            self.next_squad_id += 1
            guild_squads.append(new_squad)
            self.uid_to_squad[uid] = new_squad
            print(f"[SQUAD #{new_squad.id}] 🆕 Created for guild {guild_id}", flush=True)
            return new_squad

    async def release_squad(self, squad: Squad):
        async with self.lock:
            for uid in list(squad.members.keys()):
                self.uid_to_squad.pop(uid, None)
            guild_squads = self.squads_by_guild.get(squad.guild_id, [])
            if squad in guild_squads:
                guild_squads.remove(squad)
            squad.members.clear()
            squad.full_event.clear()
            squad.in_match = False

    def stats(self) -> Dict[str, Any]:
        all_squads = []
        for gid, squads in self.squads_by_guild.items():
            for sq in squads:
                all_squads.append({
                    "id": sq.id,
                    "guild_id": sq.guild_id,
                    "filled": len(sq.members),
                    "max": sq.size,
                    "leader": sq.leader_uid,
                    "in_match": sq.in_match,
                    "matches": sq.match_count,
                    "members": list(sq.members.keys()),
                })
        return {
            "squad_size": self.squad_size,
            "total_squads": len(all_squads),
            "ready_accounts": len(self.ready_accounts),
            "ready_uids": list(self.ready_accounts),
            "squads": all_squads,
        }


squad_manager = SquadManager(squad_size=4)