# -*- coding: utf-8 -*-
# Per-Guild Folder Storage
import asyncio, json, os, time
from typing import Dict, List
from squad_manager import squad_manager

GUILDS_DIR = "guilds"
ACTIVE_GUILD_FILE = "active_guild.txt"

# ═══════════ STORAGE ═══════════
def _ensure_guild_dir(guild_id: str) -> str:
    """Return path: guilds/<gid>/"""
    gid_dir = os.path.join(GUILDS_DIR, str(guild_id).strip())
    os.makedirs(gid_dir, exist_ok=True)
    return gid_dir

def _joined_file(guild_id: str) -> str:
    return os.path.join(_ensure_guild_dir(guild_id), "joined.json")

def load_guild_joined(guild_id: str) -> Dict[str, float]:
    """Return {uid: joined_at_timestamp}"""
    path = _joined_file(guild_id)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {str(k): float(v) for k, v in data.items()}
    except Exception:
        return {}

def save_guild_joined(guild_id: str, uid: str):
    """Save uid into guilds/<gid>/joined.json"""
    data = load_guild_joined(guild_id)
    data[str(uid)] = time.time()
    try:
        with open(_joined_file(guild_id), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[STORE] save error: {e}")

def get_joined_uids(guild_id: str) -> List[str]:
    return list(load_guild_joined(guild_id).keys())

def is_joined_any_guild(uid: str) -> str:
    """Return guild_id if uid is in ANY guild folder, else ''."""
    if not os.path.exists(GUILDS_DIR):
        return ""
    uid = str(uid)
    for gid_folder in os.listdir(GUILDS_DIR):
        path = os.path.join(GUILDS_DIR, gid_folder, "joined.json")
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if uid in data:
                return gid_folder
        except Exception:
            continue
    return ""

def get_joined_age(guild_id: str, uid: str) -> float:
    data = load_guild_joined(guild_id)
    ts = data.get(str(uid))
    if ts is None: return -1
    return time.time() - ts

def clear_guild(guild_id: str):
    """Delete guilds/<gid>/ folder."""
    import shutil
    gid_dir = os.path.join(GUILDS_DIR, str(guild_id).strip())
    if os.path.exists(gid_dir):
        shutil.rmtree(gid_dir, ignore_errors=True)

def set_active_guild(guild_id: str):
    try:
        with open(ACTIVE_GUILD_FILE, "w", encoding="utf-8") as f:
            f.write(str(guild_id).strip())
    except Exception: pass

def get_active_guild() -> str:
    if not os.path.exists(ACTIVE_GUILD_FILE):
        return ""
    try:
        with open(ACTIVE_GUILD_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""

def list_all_guilds() -> Dict[str, int]:
    """Return {guild_id: count}."""
    if not os.path.exists(GUILDS_DIR):
        return {}
    out = {}
    for gid_folder in os.listdir(GUILDS_DIR):
        path = os.path.join(GUILDS_DIR, gid_folder, "joined.json")
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            out[gid_folder] = len(data)
        except Exception:
            out[gid_folder] = 0
    return out

# ═══════════ HELPERS ═══════════
def fetch_guild_info(guild_id):
    return {"id": str(guild_id), "name": "Guild", "level": 1,
            "member_count": 0, "capacity": 50, "glory": 0, "region": "IND"}

async def preload_for_guild(guild_id: str) -> int:
    uids = get_joined_uids(guild_id)
    for uid in uids:
        await squad_manager.mark_ready(str(uid))
    if uids:
        print(f"[PRELOAD] ✅ {len(uids)} UIDs ready for guild {guild_id}", flush=True)
    return len(uids)

def set_guild_target(guild_id, guild_info=None):
    set_active_guild(guild_id)
    print(f"[GUILD] Active: {guild_id}")

def stop_guild_target():
    print("[GUILD] Stopped")

def reset_joined_accounts():
    """Delete ALL guild folders."""
    import shutil
    if os.path.exists(GUILDS_DIR):
        shutil.rmtree(GUILDS_DIR, ignore_errors=True)
    if os.path.exists(ACTIVE_GUILD_FILE):
        try: os.remove(ACTIVE_GUILD_FILE)
        except Exception: pass
    print("[GUILD] All guild folders cleared")

def get_guild_state():
    active = get_active_guild()
    joined = load_guild_joined(active) if active else {}
    return {
        "enabled": bool(active),
        "guild_id": active,
        "ready_count": len(joined),
        "total_count": len(joined),
        "ready_uids": list(joined.keys()),
        "joined_accounts": {u: active for u in joined.keys()},
        "locked_count": len(joined),
        "all_guilds": list_all_guilds(),
        "accounts": {u: {"joined": True, "status": "IN_GUILD", "guild_id": active}
                     for u in joined.keys()},
        "logs": [],
    }

async def guild_check_loop(*args, **kwargs):
    while True:
        await asyncio.sleep(5.0)