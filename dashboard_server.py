# -*- coding: utf-8 -*-
"""
HACKRR GUILD GLORY BOT — Web Dashboard
Per-guild folder + level folder save + task controls
"""
import asyncio, json, os, time
from typing import Dict, List, Any, Optional
from aiohttp import web

from squad_manager import squad_manager

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "index.html")

# ═══════════ BOT STATE ═══════════
class BotState:
    def __init__(self):
        self.logs: List[Dict[str, Any]] = []
        self.max_logs = 500
        self.start_time = time.time()
        self.account_workers: Dict[str, asyncio.Task] = {}
        self.refresh_callbacks: Dict[str, Any] = {}
        self.account_credentials: Dict[str, Dict[str, Any]] = {}
        self.accounts: Dict[str, Dict[str, Any]] = {}
        self.paused_accounts: set = set()
        self.total_matches = 0
        self.total_gained_exp = 0
        self.auth_to_game_id: Dict[str, str] = {}
        self.game_to_auth_id: Dict[str, str] = {}
        self.active_writers: Dict[str, set] = {}
        self.guild_tasks: Dict[str, Dict[str, Any]] = {}

    def log(self, message: str, level: str = "info", uid: Optional[str] = None):
        entry = {"time": time.strftime("%H:%M:%S"), "level": level,
                 "message": message, "uid": str(uid) if uid else None}
        self.logs.append(entry)
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)

    def register_account(self, uid, nickname, region, level, exp, likes=0, token=None, auth_uid=None):
        uid_str = str(uid)
        auth_uid_str = str(auth_uid) if auth_uid else self.game_to_auth_id.get(uid_str, "")
        if auth_uid_str:
            self.auth_to_game_id[auth_uid_str] = uid_str
            self.game_to_auth_id[uid_str] = auth_uid_str
        if uid_str not in self.accounts:
            self.accounts[uid_str] = {
                "uid": uid_str, "auth_uid": auth_uid_str or "",
                "nickname": nickname or f"Player_{uid_str[:6]}",
                "region": region or "IND", "level": level or 1,
                "initial_exp": exp or 0, "current_exp": exp or 0, "gained_exp": 0,
                "likes": likes or 0, "status": "ONLINE", "matches_played": 0,
                "active_matches": 0, "last_match_time": None, "token": token or "",
                "start_time": time.time(), "last_updated": time.strftime("%H:%M:%S")
            }
        else:
            acc = self.accounts[uid_str]
            if nickname: acc["nickname"] = nickname
            if region: acc["region"] = region
            if level: acc["level"] = level
            acc["current_exp"] = exp or 0
            acc["gained_exp"] = max(0, (exp or 0) - acc["initial_exp"])
            acc["last_updated"] = time.strftime("%H:%M:%S")

    def update_status(self, uid, status, active_matches=None):
        uid_str = str(uid)
        if uid_str in self.accounts:
            self.accounts[uid_str]["status"] = status
            if active_matches is not None:
                self.accounts[uid_str]["active_matches"] = active_matches
            self.accounts[uid_str]["last_updated"] = time.strftime("%H:%M:%S")

    def update_exp(self, uid, current_exp, level=None):
        uid_str = str(uid)
        if uid_str in self.accounts:
            acc = self.accounts[uid_str]
            acc["current_exp"] = current_exp
            if level is not None and level > 0: acc["level"] = level
            acc["gained_exp"] = max(0, current_exp - acc["initial_exp"])
            self.total_gained_exp = sum(a.get("gained_exp", 0) for a in self.accounts.values())
            acc["last_updated"] = time.strftime("%H:%M:%S")

    def increment_match(self, uid):
        uid_str = str(uid)
        self.total_matches += 1
        if uid_str in self.accounts:
            self.accounts[uid_str]["matches_played"] += 1
            self.accounts[uid_str]["last_match_time"] = time.strftime("%H:%M:%S")

    def is_paused(self, uid): return str(uid) in self.paused_accounts

bot_state = BotState()

FALLBACK_HTML = """<!DOCTYPE html><html><head><title>HACKRR</title></head>
<body style="background:#080d17;color:#fff;text-align:center;padding:50px">
<h1>HACKRR GUILD GLORY BOT</h1><p>templates/index.html missing</p></body></html>"""

# ═══════════ HELPERS ═══════════
GUILDS_DIR = "guilds"
ACCOUNT_LVL_DIR = "Account lvl"
ACCOUNTS_FILE = "accounts.json"


def _guild_joined_file(gid): return os.path.join(GUILDS_DIR, str(gid), "joined.json")

def _load_guild_joined(gid):
    path = _guild_joined_file(gid)
    if not os.path.exists(path): return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception: return {}

def _save_guild_joined(gid, data):
    path = _guild_joined_file(gid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def _load_all_guilds():
    if not os.path.exists(GUILDS_DIR): return {}
    out = {}
    for d in os.listdir(GUILDS_DIR):
        if os.path.isdir(os.path.join(GUILDS_DIR, d)):
            joined = _load_guild_joined(d)
            out[d] = {"count": len(joined), "joined": joined}
    return out

def _load_accounts():
    if not os.path.exists(ACCOUNTS_FILE): return []
    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except Exception: return []


# ═══════════ LEVEL FOLDER SAVE ═══════════
def _lvl_folder(region):
    return os.path.join(ACCOUNT_LVL_DIR, (region or "IND").upper().lower())

def _lvl_file(region, level):
    return os.path.join(_lvl_folder(region), f"{int(level)}lvl_account.json")

def _read_lvl(path):
    if not os.path.exists(path): return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except Exception: return []

def _write_lvl(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def save_account_to_level_folder(account_data):
    """Save account to Account lvl/<region>/<level>lvl_account.json"""
    try:
        game_uid = str(account_data.get("account_id", "") or "")
        auth_uid = str(account_data.get("auth_uid", "") or "")
        if not game_uid and not auth_uid: return
        nickname = account_data.get("nickname", "") or ""
        level = max(1, min(100, int(account_data.get("level", 1) or 1)))
        region = (account_data.get("region") or "IND").upper()

        folder = _lvl_folder(region)
        if os.path.isdir(folder):
            for fname in list(os.listdir(folder)):
                if not fname.endswith("lvl_account.json"): continue
                try: lvl = int(fname.replace("lvl_account.json", ""))
                except: continue
                if lvl == level: continue
                fp = os.path.join(folder, fname)
                data = _read_lvl(fp)
                new_data = [a for a in data if not (
                    str(a.get("game_uid", "")) == game_uid or
                    (auth_uid and str(a.get("uid", "")) == auth_uid)
                )]
                if len(new_data) != len(data):
                    if new_data: _write_lvl(fp, new_data)
                    else:
                        try: os.remove(fp)
                        except: pass

        path = _lvl_file(region, level)
        data = _read_lvl(path)
        pwd = account_data.get("auth_password", "")
        if not pwd and auth_uid:
            for a in _load_accounts():
                if str(a.get("uid", "")) == auth_uid:
                    pwd = a.get("password", ""); break

        entry = {
            "uid": auth_uid,
            "password": pwd,
            "game_uid": game_uid,
            "nickname": nickname,
            "level": level,
            "region": region,
        }
        idx = -1
        for i, a in enumerate(data):
            if str(a.get("game_uid", "")) == game_uid or (auth_uid and str(a.get("uid", "")) == auth_uid):
                idx = i; break
        if idx >= 0: data[idx] = entry
        else: data.append(entry)
        _write_lvl(path, data)
    except Exception as e:
        bot_state.log(f"[LVL] save failed: {e}", "error")


# ═══════════ HANDLERS ═══════════
async def handle_index(request):
    content = FALLBACK_HTML
    if os.path.exists(TEMPLATE_PATH):
        try:
            with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
                content = f.read()
        except: pass
    return web.Response(text=content, content_type="text/html", charset="utf-8")


async def handle_get_stats(request):
    return web.json_response({
        "total_matches": bot_state.total_matches,
        "accounts": list(bot_state.accounts.values()),
        "logs": bot_state.logs[-100:],
        "uptime": max(1, int(time.time() - bot_state.start_time))
    })


async def handle_guilds_list(request):
    guilds = _load_all_guilds()
    for gid, info in guilds.items():
        task_info = bot_state.guild_tasks.get(gid, {})
        info["status"] = task_info.get("status", "idle")
        info["uids"] = list(info["joined"].keys())
    return web.json_response({"status": "ok", "guilds": guilds})


async def handle_guild_join(request):
    try:
        data = await request.json()
        gid = str(data.get("guild_id", "")).strip()
        num_bots = int(data.get("num_bots", 4))
        if not gid:
            return web.json_response({"status": "error", "error": "guild_id required"})

        joined = _load_guild_joined(gid)
        already_uids = set(str(k) for k in joined.keys())
        max_batch = max([float(v) for v in joined.values()], default=0.0)
        next_batch = max_batch + 1.0

        all_acc = _load_accounts()
        fresh = []
        for a in all_acc:
            uid = str(a.get("uid", "")).strip()
            if not uid or not a.get("password"): continue
            if uid in already_uids: continue
            skip = False
            for og, oinfo in _load_all_guilds().items():
                if uid in oinfo["joined"]: skip = True; break
            if skip: continue
            fresh.append(a)

        to_join = fresh[:num_bots]
        if not to_join:
            return web.json_response({
                "status": "error",
                "error": f"No fresh accounts (all {len(already_uids)} already in some guild)"
            })

        from join_guild import do_join, call_with_retry

        async def bg_join():
            loop = asyncio.get_running_loop()
            ok = 0
            bot_state.log(f"🚀 Joining {len(to_join)} accounts → guild {gid} (batch {next_batch})", "info")
            for acc in to_join:
                uid = str(acc["uid"])
                pwd = str(acc["password"])
                try:
                    result = await loop.run_in_executor(
                        None,
                        lambda u=uid, p=pwd: call_with_retry(do_join, gid, u, p, max_retries=2)
                    )
                    if result[0]:
                        cur = _load_guild_joined(gid)
                        cur[uid] = next_batch
                        _save_guild_joined(gid, cur)
                        ok += 1
                        bot_state.log(f"✅ {uid} joined (batch {next_batch}) — {ok}/{len(to_join)}", "success")
                    else:
                        bot_state.log(f"❌ {uid} failed (HTTP {result[1]})", "error")
                except Exception as e:
                    bot_state.log(f"❌ {uid} error: {e}", "error")
                await asyncio.sleep(0.3)
            bot_state.log(f"🎯 Guild {gid} join done: {ok}/{len(to_join)}", "success")

            await _start_guild_task(gid)

        asyncio.create_task(bg_join())

        return web.json_response({
            "status": "ok",
            "pending": len(to_join),
            "batch": next_batch,
            "message": f"Joining {len(to_join)} accounts in background"
        })
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def _start_guild_task(gid):
    """Start worker for all joined UIDs of a guild"""
    joined = _load_guild_joined(gid)
    if not joined:
        bot_state.log(f"[G{gid}] No joined UIDs — cannot start", "warning")
        return False

    await _stop_guild_task(gid, silent=True)

    all_acc = _load_accounts()
    uid_map = {str(a.get("uid", "")): a for a in all_acc}

    uids = list(joined.keys())
    task_info = {"uids": uids, "tasks": [], "status": "running"}
    bot_state.guild_tasks[gid] = task_info

    spawn_fn = bot_state.refresh_callbacks.get("on_spawn_worker")
    if not spawn_fn:
        bot_state.log(f"[G{gid}] ❌ spawn_worker callback not registered", "error")
        return False

    started = 0
    for uid in uids:
        if uid not in uid_map:
            bot_state.log(f"[G{gid}] {uid} not in accounts.json — skip", "warning")
            continue
        pwd = str(uid_map[uid]["password"])
        await squad_manager.mark_ready(uid)
        try:
            t = spawn_fn(uid, pwd, gid)
        except Exception as e:
            bot_state.log(f"[G{gid}] spawn err {uid}: {e}", "error")
            t = None
        if t:
            bot_state.account_workers[f"{gid}:{uid}"] = t
            task_info["tasks"].append(t)
            started += 1

    bot_state.log(f"[G{gid}] 🚀 Started {started} workers ({len(uids)} joined)", "success")
    return started > 0


async def _stop_guild_task(gid, silent=False):
    info = bot_state.guild_tasks.get(gid)
    if not info:
        if not silent:
            bot_state.log(f"[G{gid}] No task to stop", "warning")
        return
    for t in info.get("tasks", []):
        if not t.done():
            try: t.cancel()
            except: pass
    for k in list(bot_state.account_workers.keys()):
        if k.startswith(f"{gid}:"):
            bot_state.account_workers.pop(k, None)
    info["status"] = "stopped"
    info["tasks"] = []
    bot_state.log(f"[G{gid}] ⏹ Task stopped", "warning")


async def handle_guild_task(request):
    try:
        data = await request.json()
        gid = str(data.get("guild_id", "")).strip()
        action = str(data.get("action", "")).strip().lower()
        if not gid or action not in ("start", "stop", "restart", "delete"):
            return web.json_response({"status": "error", "error": "invalid params"})

        if action == "start":
            ok = await _start_guild_task(gid)
            return web.json_response({"status": "ok" if ok else "error",
                                       "msg": "started" if ok else "no joined uids"})
        elif action == "stop":
            await _stop_guild_task(gid)
            return web.json_response({"status": "ok"})
        elif action == "restart":
            await _stop_guild_task(gid, silent=True)
            await asyncio.sleep(1.0)
            ok = await _start_guild_task(gid)
            return web.json_response({"status": "ok" if ok else "error"})
        elif action == "delete":
            await _stop_guild_task(gid, silent=True)
            import shutil
            folder = os.path.join(GUILDS_DIR, gid)
            if os.path.exists(folder):
                shutil.rmtree(folder, ignore_errors=True)
            bot_state.guild_tasks.pop(gid, None)
            bot_state.log(f"[G{gid}] 🗑 Deleted", "warning")
            return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_clear_logs(request):
    bot_state.logs.clear()
    return web.json_response({"status": "ok"})


# ═══════════ ROUTES ═══════════
async def start_web_dashboard(host="0.0.0.0", port=20333):
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/stats", handle_get_stats)
    app.router.add_get("/api/guilds", handle_guilds_list)
    app.router.add_post("/api/guild/join", handle_guild_join)
    app.router.add_post("/api/guild/task", handle_guild_task)
    app.router.add_post("/api/logs/clear", handle_clear_logs)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    print(f"[DASHBOARD] ✅ http://localhost:{port}", flush=True)
    return runner