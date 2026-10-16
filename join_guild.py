# =============================================================================
#  GREAT JOHIR v5.2 — Guild Join (Per-Guild Folder)
#  Saves to guilds/<gid>/joined.json
# =============================================================================
import os, sys, re, time, json, threading, random
import urllib.parse, urllib.request, urllib.error, ssl, concurrent.futures
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from guild_auto_join import (
    save_guild_joined, load_guild_joined,
    is_joined_any_guild, set_active_guild
)

# ═══════════ THEME ═══════════
class T:
    RESET="\033[0m"; BOLD="\033[1m"; DIM="\033[2m"
    RED="\033[38;5;203m"; BLOOD="\033[38;5;196m"; GOLD="\033[38;5;220m"
    AMBER="\033[38;5;214m"; CYAN="\033[38;5;80m"; GREEN="\033[38;5;78m"
    LIME="\033[38;5;154m"; PINK="\033[38;5;212m"; TEAL="\033[38;5;44m"
    VIOLET="\033[38;5;141m"; WHITE="\033[38;5;255m"; GREY="\033[38;5;245m"

def term_w():
    try: return max(56, os.get_terminal_size().columns)
    except: return 90

def term_c(s, width=None):
    w = width or term_w()
    v = len(re.sub(r"\033\[[0-9;]*m", "", s))
    if v >= w: return s
    return " " * ((w - v) // 2) + s

# ═══════════ HTTP ═══════════
_ssl = ssl.create_default_context()
_ssl.check_hostname = False; _ssl.verify_mode = ssl.CERT_NONE
BASE = "https://danger-guild-management-web.vercel.app"
JOIN_URL = f"{BASE}/join"
UA = "Mozilla/5.0 (Linux; Android 10) GREAT_JOHIR/5.2"

def _get(url, timeout=20):
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA, "Accept": "application/json, text/plain, */*",
            "Connection": "close",
        })
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl) as r:
            return True, r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try: body = e.read().decode("utf-8", "replace")
        except: body = ""
        return False, e.code, body
    except Exception as e:
        return False, 0, str(e)

def do_join(gid, uid, pwd):
    q = urllib.parse.urlencode({"guild_id": gid, "uid": uid, "password": pwd})
    return _get(f"{JOIN_URL}?{q}")

def do_leave(gid, uid, pwd):
    for ep in [f"{BASE}/leave", f"{BASE}/guild/leave"]:
        q = urllib.parse.urlencode({"guild_id": gid, "uid": uid, "password": pwd})
        ok, code, body = _get(f"{ep}?{q}")
        if ok: return ok, code, body
    return False, 0, ""

def call_with_retry(fn, gid, uid, pwd, max_retries=3):
    backoff = 0.6
    for attempt in range(max_retries + 1):
        try:
            ok, code, body = fn(gid, uid, pwd)
            if ok: return ok, code, body, "", attempt
            if code == 429 or 500 <= code < 600:
                time.sleep(backoff); backoff *= 2; continue
            return ok, code, body, "", attempt
        except Exception:
            time.sleep(backoff); backoff *= 2
    return False, 0, "", "", max_retries

def _save_joined_uid(uid, guild_id):
    save_guild_joined(guild_id, uid)

def load_accounts(path):
    if not os.path.isfile(path):
        return None, f"file not found: {path}"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        out, seen = [], set()
        for item in data:
            u, p = item.get('uid'), item.get('password')
            if u and p and str(u) not in seen:
                seen.add(str(u)); out.append((str(u), str(p)))
        return out, None
    except Exception as e:
        return None, str(e)

# ═══════════ MAIN ═══════════
def main():
    print(term_c(f"{T.GOLD}{T.BOLD}✦ GREAT JOHIR v5.2 — Per-Guild Folder ✦{T.RESET}\n"))

    src = input(f"{T.CYAN}📂 accounts.json path [{T.WHITE}accounts.json{T.CYAN}]: {T.RESET}").strip() or "accounts.json"
    accounts, err = load_accounts(src)
    if err:
        print(f"{T.BLOOD}✘ {err}{T.RESET}"); return
    print(f"{T.GREEN}✔ Loaded {len(accounts)} accounts{T.RESET}")

    gid = input(f"{T.CYAN}🏰 Guild ID: {T.RESET}").strip()
    if not gid:
        print(f"{T.BLOOD}✘ Guild ID required{T.RESET}"); return

    # Filter out already-joined
    to_join = []
    for (u, p) in accounts:
        existing = is_joined_any_guild(u)
        if existing:
            if existing == gid:
                print(f"{T.DIM}  skip {u} (already in THIS guild){T.RESET}")
            else:
                print(f"{T.AMBER}  skip {u} (in guild {existing}){T.RESET}")
            continue
        to_join.append((u, p))

    if not to_join:
        print(f"{T.LIME}✅ No fresh accounts to join.{T.RESET}")
        return

    try: workers = max(1, min(10, int(input(f"{T.CYAN}⚡ Workers [{T.WHITE}4{T.CYAN}]: {T.RESET}").strip() or "4")))
    except: workers = 4

    print(f"\n{T.CYAN}▶ Joining {len(to_join)} accounts to guild {gid}...{T.RESET}\n")

    total = len(to_join)
    ok_count = 0
    lock = threading.Lock()

    def worker(uid, pwd):
        nonlocal ok_count
        ok, code, body, _, retries = call_with_retry(do_join, gid, uid, pwd, max_retries=3)
        msg = ""
        try:
            if body:
                j = json.loads(body)
                msg = str(j.get("message") or j.get("msg") or j.get("error") or "")[:60]
        except Exception:
            msg = (body or "")[:60].replace("\n", " ")

        if ok:
            save_guild_joined(gid, uid)
            with lock: ok_count += 1
            print(f"{T.GREEN}✔ {uid} → joined ({msg}){T.RESET}")
        else:
            print(f"{T.RED}✘ {uid} → HTTP {code} ({msg}){T.RESET}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(worker, u, p) for u, p in to_join]
        concurrent.futures.wait(futs)

    set_active_guild(gid)

    print(f"\n{T.GOLD}{T.BOLD}═════════════════════════════════════════{T.RESET}")
    print(f"{T.LIME}✔ Success : {ok_count}/{total}{T.RESET}")
    print(f"{T.PINK}💾 Saved   : guilds/{gid}/joined.json{T.RESET}")
    print(f"{T.GOLD}🎯 Active  : {gid}{T.RESET}")
    print(f"{T.GOLD}{T.BOLD}═════════════════════════════════════════{T.RESET}")

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt:
        print(f"\n{T.AMBER}stopped{T.RESET}")