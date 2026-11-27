# -*- coding: utf-8 -*-
"""
FreeFire Level Up Bot - Professional Web Dashboard & Real-Time EXP Tracker
Embedded Async Web Server (aiohttp)
Optimized for ultra-smooth operation, zero memory leaks, and dynamic multi-account control.
"""

import asyncio
import json
import os
import time
from typing import Dict, List, Any, Optional
from aiohttp import web
import urllib3
import requests
import httpx
import jwt
try:
    import gen as account_generator
except ImportError:
    account_generator = None
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import ReqCLan_pb2
import encode_id_clan_pb2
import data_pb2
import output_pb2
from google.protobuf.json_format import MessageToDict

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Web_temp", "web.html")
if not os.path.exists(TEMPLATE_PATH):
    TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web.html")

# External guild APIs supplied for the dashboard setup flow.
GUILD_JOIN_API = "https://ngsujeetguild-manejar.vercel.app/Join"
GUILD_INFO_API = "https://danger-guild-management-web.vercel.app/guild"
GUILD_CONFIG_FILE = "guild_config.json"

OB = "OB55"
KEY = bytes([89,103,38,116,99,37,68,69,117,104,54,37,90,99,94,56])
IV  = bytes([54,111,121,90,68,114,50,50,69,51,121,99,104,106,77,37])

GAME_HEADERS = {
    "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9)",
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/octet-stream",
    "X-Unity-Version": "2018.4.11f1",
    "X-GA": "v1 1",
    "ReleaseVersion": OB,
    "Expect": "100-continue"
}

REGION_SERVER_MAP = {
    "IND": ("https://clientbp.freefireind.in", "clientbp.freefireind.in"),
    "ME":  ("https://clientbp.ggblueshark.com", "clientbp.ggblueshark.com"),
    "VN":  ("https://clientbp.ggpolarbear.com", "clientbp.ggpolarbear.com"),
    "BD":  ("https://clientbp.ggwhitehawk.com", "clientbp.ggwhitehawk.com"),
    "PK":  ("https://clientbp.ggblueshark.com", "clientbp.ggblueshark.com"),
    "SG":  ("https://clientbp.ggpolarbear.com", "clientbp.ggpolarbear.com"),
    "BR":  ("https://client.us.freefiremobile.com", "client.us.freefiremobile.com"),
    "NA":  ("https://client.us.freefiremobile.com", "client.us.freefiremobile.com"),
    "ID":  ("https://clientbp.ggpolarbear.com", "clientbp.ggpolarbear.com"),
    "RU":  ("https://clientbp.ggpolarbear.com", "clientbp.ggpolarbear.com"),
    "TH":  ("https://clientbp.ggpolarbear.com", "clientbp.ggpolarbear.com"),
    "SAC": ("https://client.br.freefiremobile.com", "client.br.freefiremobile.com"),
    "TW":  ("https://client.tw.freefiremobile.com", "client.tw.freefiremobile.com"),
    "CIS": ("https://client.cis.freefiremobile.com", "client.cis.freefiremobile.com"),
}
DEFAULT_SERVER_URL = "https://clientbp.ggblueshark.com"
DEFAULT_HOST = "clientbp.ggblueshark.com"

def encrypt_payload(data):
    cipher = AES.new(KEY, AES.MODE_CBC, IV)
    return cipher.encrypt(pad(data, AES.block_size))

def get_server_info(region):
    val = REGION_SERVER_MAP.get(str(region).upper(), DEFAULT_SERVER_URL)
    if isinstance(val, tuple):
        return val
    return (val, DEFAULT_HOST)

def get_server_url(region):
    info = get_server_info(region)
    return info[0] if isinstance(info, tuple) else info

def fetch_single_clan(clan_id, region, token_cache):
    server_base, host = get_server_info(region)
    url = f"{server_base}/GetClanInfoByClanID"

    try:  
        my_data = encode_id_clan_pb2.MyData()  
        my_data.field1 = int(clan_id)  
        my_data.field2 = 1  
        payload = encrypt_payload(my_data.SerializeToString())  
    except Exception as e:
        return {"clan_id": clan_id, "error": f"Protobuf failed: {str(e)}"}

    response = None
    attempts = []
    for uid, creds in token_cache.items():
        token = creds.get('token')
        if not token:
            continue

        headers = GAME_HEADERS.copy()
        headers["Authorization"] = f"Bearer {token}" if not token.startswith("Bearer ") else token
        headers["Host"] = host

        try:
            res = requests.post(url, headers=headers, data=payload, verify=False, timeout=15.0)
            if res.status_code == 200:
                response = res
                break
            attempts.append(f"{uid}: HTTP {res.status_code}")
            if "expired" in res.text.lower() or res.status_code == 401:
                continue
            response = res
            break
        except Exception as ex:
            attempts.append(f"{uid}: {type(ex).__name__}")
            continue

    if not response or response.status_code != 200:
        detail = "; ".join(attempts[:4])
        return {"clan_id": int(clan_id), "error": "No account token could read this guild" + (f" ({detail})" if detail else "")}

    full_response = {}
    resp = None
    try:
        resp = data_pb2.response()
        resp.ParseFromString(response.content)
        full_response = MessageToDict(resp, preserving_proto_field_name=True)
    except Exception as e:
        return {"clan_id": int(clan_id), "error": f"Guild response decode failed: {e}"}

    # data.proto defines xp as field 39; field 36 is rank, not guild glory.
    guild_xp = int(getattr(resp, "xp", 0) or 0)
    gd = resp.guild_details if resp.HasField("guild_details") else None
    return {
        "captain_id": int(getattr(gd, "leader_uid", 0) or 0) if gd else 0,
        "clan_id": int(clan_id),
        "clan_level": int(getattr(gd, "level", 0) or 0) or None if gd else None,
        "clan_name": (getattr(gd, "name", "") or f"Guild_{clan_id}") if gd else f"Guild_{clan_id}",
        "current_members": int(getattr(gd, "total_members", 0) or 0) or None if gd else None,
        "members_online": int(getattr(gd, "members_online", 0) or 0) or None if gd else None,
        "max_members": None,
        "Total guild xp": guild_xp,
        "glory": guild_xp,
        "xp": guild_xp,
        "welcome_message": (getattr(gd, "notice", "") if gd else "") or getattr(resp, "welcome_message", ""),
        "region": region,
        "raw_response_bytes": response.content.hex()
    }

async def request_clan_async(jwt_token, clan_id, region):
    server_url = get_server_url(region)
    msg = ReqCLan_pb2.MyMessage()
    msg.field_1 = int(clan_id)
    payload = encrypt_payload(msg.SerializeToString())
    headers = GAME_HEADERS.copy()
    headers["Authorization"] = f"Bearer {jwt_token}" if not jwt_token.startswith("Bearer ") else jwt_token
    url = f"{server_url}/RequestJoinClan"
    async with httpx.AsyncClient(verify=False, timeout=8.0) as client:
        r = await client.post(url, headers=headers, content=payload)
        return r.status_code, r.text

EXP_TABLE: Dict[int, int] = {
    1: 0, 2: 48, 3: 202, 4: 544, 5: 1012, 6: 1844, 7: 2792, 8: 3800,
    9: 4870, 10: 6004, 11: 7192, 12: 8448, 13: 9760, 14: 11140, 15: 12566,
    16: 14060, 17: 15610, 18: 17224, 19: 18902, 20: 20632, 21: 22424, 22: 24278,
    23: 26192, 24: 28166, 25: 30200, 26: 32294, 27: 34448, 28: 37804, 29: 41274,
    30: 44870, 31: 48582, 32: 53394, 33: 58566, 34: 64096, 35: 69994, 36: 76460,
    37: 83506, 38: 91128, 39: 99322, 40: 108092, 41: 120144, 42: 133266, 43: 147472,
    44: 162760, 45: 179126, 46: 196572, 47: 215368, 48: 235516, 49: 257010, 50: 279860,
    51: 304056, 52: 348318, 53: 394982, 54: 444044, 55: 495508, 56: 549364, 57: 633756,
    58: 721744, 59: 813336, 60: 908522, 61: 1041438, 62: 1180352, 63: 1325266,
    64: 1476184, 65: 1634300, 66: 1840946, 67: 2056594, 68: 2281242, 69: 2514880,
    70: 2757530, 71: 3059506, 72: 3372284, 73: 3699456, 74: 4041030, 75: 4397002,
    76: 4829104, 77: 5282204, 78: 5756304, 79: 6251408, 80: 6776502, 81: 7381324,
    82: 8043154, 83: 8752982, 84: 9510808, 85: 10316338, 86: 11277190, 87: 12291748,
    88: 13360304, 89: 14482858, 90: 15659418, 91: 17026708, 92: 18453950, 93: 19941280,
    94: 21488570, 95: 23095858, 96: 24763138, 97: 26490428, 98: 28378704, 99: 30124996,
    100: 32032884
}

async def handle_index(request: web.Request) -> web.Response:
    content = FALLBACK_INDEX_HTML
    if os.path.exists(TEMPLATE_PATH):
        try:
            with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            pass
    return web.Response(text=content, content_type="text/html", charset="utf-8")


BANNED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "banned_accounts.json")

# ---- Purane accounts: accounts.json har baar "fresh pool" mein khaali ho jata hai, isliye purane accounts ka
# ---- automatic archive (accounts_archive.json) rakhte hain. Dashboard se jab chaho unhe wapas activate kar sakte ho.
ARCHIVE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "accounts_archive.json")

def _read_json_list(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []

def _write_json_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)

def _archive_accounts():
    """accounts.json ke saare (uid+password) accounts ko archive mein jod deta hai (duplicate nahi)."""
    try:
        cur = _read_json_list("accounts.json")
        arc = _read_json_list(ARCHIVE_FILE)
        have = {str(a.get("uid", "")) for a in arc}
        added = 0
        for a in cur:
            uid = str(a.get("uid", "")).strip(); pwd = str(a.get("password", "")).strip()
            if uid and pwd and uid not in have:
                arc.append({"uid": uid, "password": pwd, "saved_at": int(time.time())}); have.add(uid); added += 1
        if added:
            _write_json_atomic(ARCHIVE_FILE, arc)
        return added
    except Exception:
        return 0

def _running_guest_uids():
    return {str(k) for k, t in bot_state.account_workers.items() if t is not None and not t.done()}

def _banned_keys():
    try:
        with open(BANNED_FILE, "r", encoding="utf-8") as f:
            return {str(k) for k in (json.load(f) or {}).keys()}
    except Exception:
        return {str(k) for k in bot_state.banned_accounts.keys()}

def _old_accounts_snapshot():
    """Archive mein jo accounts abhi chal nahi rahe (aur banned nahi) - dashboard 'Purane accounts' ke liye. Password nahi bhejte."""
    arc = _read_json_list(ARCHIVE_FILE)
    running = _running_guest_uids(); banned = _banned_keys()
    inactive = [str(a["uid"]) for a in arc if a.get("uid") and a.get("password") and str(a["uid"]) not in running and str(a["uid"]) not in banned]
    return {"total": len(arc), "inactive": inactive[:300], "inactive_count": len(inactive),
            "banned": sum(1 for a in arc if str(a.get("uid", "")) in banned)}

async def handle_activate_old(request: web.Request) -> web.Response:
    """Purane (archive wale) accounts ko wapas active karta hai - wo apna kaam (squad mein judna aur khelna) shuru kar dete hain."""
    try:
        try:
            body = await request.json()
        except Exception:
            body = {}
        want_all = bool(body.get("all"))
        want = [str(u).strip() for u in (body.get("uids") or [])]
        arc = {str(a["uid"]): a for a in _read_json_list(ARCHIVE_FILE) if a.get("uid") and a.get("password")}
        running = _running_guest_uids(); banned = _banned_keys()
        pool = list(arc.keys()) if want_all else want
        targets = [u for u in pool if u in arc and u not in running and u not in banned]
        if not targets:
            return web.json_response({"status": "ok", "activated": 0, "message": "Koi purana account activate karne layak nahi (sab chal rahe hain ya banned hain)"})
        existing = _read_json_list("accounts.json")
        have = {str(a.get("uid", "")) for a in existing}
        for u in targets:
            if u not in have:
                existing.append({"uid": u, "password": arc[u]["password"]})
        _write_json_atomic("accounts.json", existing)
        cb = bot_state.refresh_callbacks.get("on_account_added")
        if cb and bot_state.glory_started:
            async def _go():
                for u in targets:
                    try:
                        await cb({"uid": u, "password": arc[u]["password"]})
                    except Exception as e:
                        bot_state.log(f"Purana account {u} start nahi hua: {e}", "error")
                    await asyncio.sleep(1.0)       # ek saath sab login na ho
            asyncio.create_task(_go())
            msg = f"{len(targets)} purane account activate ho rahe hain - squad mein judkar apna kaam shuru karenge"
        else:
            msg = f"{len(targets)} purane account accounts.json mein wapas daal diye - Glory start hote hi ye bhi chalenge"
        bot_state.log(msg, "success")
        return web.json_response({"status": "ok", "activated": len(targets), "message": msg})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})

def _banned_snapshot():
    """banned_accounts.json (app.py likhta hai) + memory se banned accounts ki list, dashboard ke liye."""
    data = {}
    try:
        with open(BANNED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
    except Exception:
        data = dict(bot_state.banned_accounts)
    out = []
    for k, v in data.items():
        if isinstance(v, dict):
            row = {kk: vv for kk, vv in v.items() if isinstance(vv, (str, int, float, bool))}
            row["key"] = str(k)
            out.append(row)
    out.sort(key=lambda r: r.get("found_at", 0), reverse=True)
    return out

async def handle_get_stats(request: web.Request) -> web.Response:
    try:
        _log_n = max(1, min(200, int(request.query.get("logs", 80))))
    except Exception:
        _log_n = 80
    accounts_data = []
    for original in bot_state.accounts.values():
        safe_account = dict(original)
        for secret_key in ("token", "access_token", "auth_token", "auth_password", "open_id", "aes_ak", "iv_i", "login_payload_data"):
            safe_account.pop(secret_key, None)
        accounts_data.append(safe_account)
    accounts_data.sort(key=lambda x: x.get("gained_exp", 0), reverse=True)
    uptime_sec = max(1, int(time.time() - bot_state.start_time))
    total_gained = bot_state.total_gained_exp
    exp_per_hour = int((total_gained / uptime_sec) * 3600)
    total_active_matches = sum(acc.get("active_matches", 0) for acc in accounts_data)

    for acc in accounts_data:
        uid_k = str(acc.get("uid", ""))
        acc["uptime_seconds"] = bot_state.get_account_uptime(uid_k)
        acc["is_paused"] = bot_state.is_paused(uid_k)

    return web.json_response({
        "total_accounts": len(bot_state.accounts),
        "total_matches": bot_state.total_matches,
        "total_matches_started": bot_state.total_matches_started,   # 🔥 NEW
        "total_active_matches": total_active_matches,
        "total_gained_exp": total_gained,
        "exp_per_hour": exp_per_hour,
        "accounts": accounts_data,
        "logs": bot_state.logs[-_log_n:],
        "relogins": bot_state.relogin_events,
        "banned": _banned_snapshot(),
        "squads": bot_state.squad_info,
        "guild": bot_state.guild_config,
        "guild_live": bot_state.guild_live,
        "automation": bot_state.automation,
        "old_accounts": _old_accounts_snapshot(),
        "uptime": uptime_sec
    })

def calculate_level_progress(level: int, current_exp: int) -> Dict[str, Any]:
    level = max(1, level)
    next_level = min(100, level + 1)
    base_exp = EXP_TABLE.get(level, 0)
    target_exp = EXP_TABLE.get(next_level, base_exp + 50000)
    
    needed_for_level = max(1, target_exp - base_exp)
    earned_in_level = max(0, current_exp - base_exp)
    remaining_exp = max(0, target_exp - current_exp)
    progress_pct = min(100.0, max(0.0, (earned_in_level / needed_for_level) * 100.0))

    return {
        "next_level": next_level,
        "base_exp": base_exp,
        "target_exp": target_exp,
        "needed_for_level": needed_for_level,
        "earned_in_level": earned_in_level,
        "remaining_exp": remaining_exp,
        "progress_pct": round(progress_pct, 1)
    }

class BotState:
    def __init__(self):
        self.accounts: Dict[str, Dict[str, Any]] = {}
        self.logs: List[Dict[str, Any]] = []
        self.max_logs = 200
        self.total_matches = 0
        self.total_matches_started = 0      # 🔥 NEW
        self.total_gained_exp = 0
        self.start_time = time.time()
        self.account_workers: Dict[str, asyncio.Task] = {}
        self.account_token_map: Dict[str, str] = {}  # uid -> token or token_prefix -> uid
        self.auth_to_game_id: Dict[str, str] = {}   # guest login uid -> in-game account id
        self.game_to_auth_id: Dict[str, str] = {}   # in-game account id -> guest login uid
        self.paused_accounts: set = set()
        self.refresh_callbacks: Dict[str, Any] = {}
        self.account_credentials: Dict[str, Dict[str, Any]] = {}
        self.active_writers: Dict[str, set] = {}
        self.glory_started = False
        self.setup_complete = False
        self.guild_config: Dict[str, Any] = {}
        self.automation: Dict[str, Any] = {"running": False, "stage": "idle", "target": 0, "created": 0, "joined": 0, "failed": 0, "message": "Ready", "started_at": None}
        self.automation_task = None
        self.relogin_events: Dict[str, Dict[str, Any]] = {}   # game uid -> re-login history (dashboard panel)
        self.guild_live: Dict[str, Any] = {}                  # live guild glory / gain / members (dashboard panel)
        self.banned_accounts: Dict[str, Dict[str, Any]] = {}  # banned accounts (login retry band) - dashboard panel
        self.squad_info: Dict[str, Dict[str, Any]] = {}       # squad-wise registered/playing/waiting (dashboard sections)

    def register_writer(self, uid: str, writer):
        uid_str = str(uid)
        if uid_str not in self.active_writers:
            self.active_writers[uid_str] = set()
        self.active_writers[uid_str].add(writer)

    def unregister_writer(self, uid: str, writer):
        uid_str = str(uid)
        if uid_str in self.active_writers:
            self.active_writers[uid_str].discard(writer)
            if not self.active_writers[uid_str]:
                self.active_writers.pop(uid_str, None)

    def close_writers_for_account(self, uid: str):
        uid_str = str(uid)
        candidates = {uid_str}
        if uid_str in self.auth_to_game_id:
            candidates.add(str(self.auth_to_game_id[uid_str]))
        if uid_str in self.game_to_auth_id:
            candidates.add(str(self.game_to_auth_id[uid_str]))
        if uid_str in self.account_token_map:
            mapped = self.account_token_map[uid_str]
            candidates.add(str(mapped))
            candidates.add(str(mapped)[:16])

        for c in list(candidates):
            writers = list(self.active_writers.get(c, []))
            for w in writers:
                try:
                    if hasattr(w, "close"):
                        if hasattr(w, "is_closing"):
                            if not w.is_closing():
                                w.close()
                        else:
                            w.close()
                except Exception:
                    pass
            self.active_writers.pop(c, None)

    def log(self, message: str, level: str = "info", uid: Optional[str] = None):
        entry = {
            "time": time.strftime("%H:%M:%S"),
            "level": level,
            "message": message,
            "uid": str(uid) if uid else None
        }
        self.logs.append(entry)
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)

    def register_account(self, uid: str, nickname: str, region: str, level: int, exp: int,
                         likes: int = 0, token: Optional[str] = None, auth_uid: Optional[str] = None):
        uid_str = str(uid)
        auth_uid_str = str(auth_uid) if auth_uid else self.game_to_auth_id.get(uid_str, "")
        if auth_uid_str:
            self.auth_to_game_id[auth_uid_str] = uid_str
            self.game_to_auth_id[uid_str] = auth_uid_str
            self.account_token_map[auth_uid_str] = uid_str
            self.account_token_map[uid_str] = auth_uid_str
        if token:
            self.account_token_map[uid_str] = token
            self.account_token_map[token[:16]] = uid_str
            if auth_uid_str:
                self.account_token_map[auth_uid_str] = token

        prog = calculate_level_progress(level or 1, exp)

        lvl_val = level or 1
        acc_mode = "BR" if lvl_val < 3 else "LONE_WOLF"
        acc_mode_label = "Battle Royale (Lvl < 3)" if lvl_val < 3 else "Lone Wolf (Lvl 3+)"

        if uid_str not in self.accounts:
            self.accounts[uid_str] = {
                "uid": uid_str,
                "auth_uid": auth_uid_str or "",
                "nickname": nickname or f"Player_{uid_str[:6]}",
                "region": region or "BD",
                "level": lvl_val,
                "next_level": prog["next_level"],
                "mode": acc_mode,
                "mode_label": acc_mode_label,
                "initial_exp": exp,
                "current_exp": exp,
                "gained_exp": 0,
                "remaining_exp": prog["remaining_exp"],
                "target_exp": prog["target_exp"],
                "needed_for_level": prog["needed_for_level"],
                "earned_in_level": prog["earned_in_level"],
                "progress_pct": prog["progress_pct"],
                "likes": likes or 0,
                "status": "PAUSED" if self.is_paused(uid_str) else "ONLINE",
                "matches_played": 0,
                "active_matches": 0,
                "last_match_time": None,
                "token": token or "",
                "start_time": time.time(),
                "is_paused": self.is_paused(uid_str),
                "paused_at": time.time() if self.is_paused(uid_str) else None,
                "total_pause_duration": 0.0,
                "last_updated": time.strftime("%H:%M:%S")
            }
        else:
            acc = self.accounts[uid_str]
            if auth_uid_str:
                acc["auth_uid"] = auth_uid_str
            if nickname:
                acc["nickname"] = nickname
            if region:
                acc["region"] = region
            if level:
                acc["level"] = level
            if token:
                acc["token"] = token
            acc["current_exp"] = exp
            acc["gained_exp"] = max(0, exp - acc["initial_exp"])
            acc["next_level"] = prog["next_level"]
            acc["remaining_exp"] = prog["remaining_exp"]
            acc["target_exp"] = prog["target_exp"]
            acc["needed_for_level"] = prog["needed_for_level"]
            acc["earned_in_level"] = prog["earned_in_level"]
            acc["progress_pct"] = prog["progress_pct"]
            acc["likes"] = likes
            if not acc.get("is_paused"):
                acc["status"] = "ONLINE"
            acc["last_updated"] = time.strftime("%H:%M:%S")
        self.recalc_totals()

    def get_account_uptime(self, uid_str: str) -> int:
        acc = self.accounts.get(uid_str)
        if not acc:
            mapped = self.game_to_auth_id.get(uid_str) or self.auth_to_game_id.get(uid_str)
            if mapped and mapped in self.accounts:
                acc = self.accounts[mapped]
        if not acc:
            return 0
        start_t = acc.get("start_time", time.time())
        total_pause = acc.get("total_pause_duration", 0.0)
        if acc.get("is_paused") and acc.get("paused_at"):
            return max(0, int(acc["paused_at"] - start_t - total_pause))
        return max(0, int(time.time() - start_t - total_pause))

    def is_paused(self, uid: str) -> bool:
        uid_str = str(uid)
        if uid_str in self.paused_accounts:
            return True
        game_id = self.auth_to_game_id.get(uid_str)
        if game_id and game_id in self.paused_accounts:
            return True
        auth_uid = self.game_to_auth_id.get(uid_str)
        if auth_uid and auth_uid in self.paused_accounts:
            return True
        acc = self.accounts.get(uid_str) or (self.accounts.get(game_id) if game_id else None)
        if acc and acc.get("is_paused"):
            return True
        return False

    def toggle_pause(self, uid: str) -> bool:
        uid_str = str(uid)
        candidates = {uid_str}
        if uid_str in self.auth_to_game_id:
            candidates.add(self.auth_to_game_id[uid_str])
        if uid_str in self.game_to_auth_id:
            candidates.add(self.game_to_auth_id[uid_str])

        target_acc = None
        target_key = uid_str
        for c in candidates:
            if c in self.accounts:
                target_acc = self.accounts[c]
                target_key = c
                break

        is_now_paused = not self.is_paused(uid_str)
        if is_now_paused:
            for c in candidates:
                self.paused_accounts.add(c)
                self.close_writers_for_account(c)
            if target_acc:
                target_acc["is_paused"] = True
                target_acc["paused_at"] = time.time()
                target_acc["status"] = "PAUSED"
            nick = target_acc.get("nickname", target_key) if target_acc else target_key
            self.log(f"⏸ UID {target_key} ({nick}) matchmaking PAUSED (TCP socket disconnected).", "warning", target_key)
            if "on_pause_toggle" in self.refresh_callbacks:
                try:
                    asyncio.create_task(self.refresh_callbacks["on_pause_toggle"](target_key, True))
                except Exception:
                    pass
        else:
            for c in candidates:
                self.paused_accounts.discard(c)
            if target_acc:
                target_acc["is_paused"] = False
                if target_acc.get("paused_at"):
                    pause_dur = time.time() - target_acc["paused_at"]
                    target_acc["total_pause_duration"] = target_acc.get("total_pause_duration", 0.0) + pause_dur
                    target_acc["paused_at"] = None
                target_acc["status"] = "ONLINE"
            nick = target_acc.get("nickname", target_key) if target_acc else target_key
            self.log(f"▶ UID {target_key} ({nick}) matchmaking RESUMED.", "success", target_key)
            if "on_pause_toggle" in self.refresh_callbacks:
                try:
                    asyncio.create_task(self.refresh_callbacks["on_pause_toggle"](target_key, False))
                except Exception:
                    pass

        return is_now_paused

    def toggle_pause_all(self) -> bool:
        any_active = any(not self.is_paused(k) for k in self.accounts.keys())
        for k in list(self.accounts.keys()):
            current_paused = self.is_paused(k)
            if any_active and not current_paused:
                self.toggle_pause(k)
            elif not any_active and current_paused:
                self.toggle_pause(k)
        return any_active

    def update_exp(self, uid: str, current_exp: int, level: Optional[int] = None):
        uid_str = str(uid)
        if uid_str in self.accounts:
            acc = self.accounts[uid_str]
            old_exp = acc["current_exp"]
            old_level = acc.get("level", 1)
            acc["current_exp"] = current_exp
            if level is not None and level > 0:
                acc["level"] = level
            acc["gained_exp"] = max(0, current_exp - acc["initial_exp"])
            
            current_lvl = acc["level"]
            acc["mode"] = "BR" if current_lvl < 3 else "LONE_WOLF"
            acc["mode_label"] = "Battle Royale (Lvl < 3)" if current_lvl < 3 else "Lone Wolf (Lvl 3+)"

            prog = calculate_level_progress(acc["level"], current_exp)
            acc["next_level"] = prog["next_level"]
            acc["remaining_exp"] = prog["remaining_exp"]
            acc["target_exp"] = prog["target_exp"]
            acc["needed_for_level"] = prog["needed_for_level"]
            acc["earned_in_level"] = prog["earned_in_level"]
            acc["progress_pct"] = prog["progress_pct"]
            acc["last_updated"] = time.strftime("%H:%M:%S")

            # Check for Level 2 -> 3 Mode Transition
            if old_level < 3 and current_lvl >= 3:
                self.log(
                    f"🎉 LEVEL UP! UID {uid_str} ({acc['nickname']}) reached Level {current_lvl}! Switching from Battle Royale to Lone Wolf mode!",
                    "success",
                    uid_str
                )

            diff = current_exp - old_exp
            if diff > 0:
                self.log(
                    f"★ UID {uid_str} ({acc['nickname']}) gained +{diff:,} EXP | Level {acc['level']} [{acc['mode']}] ({prog['progress_pct']}% - {prog['remaining_exp']:,} EXP to Lvl {prog['next_level']})",
                    "success",
                    uid_str
                )
            self.recalc_totals()

    def get_account_level(self, uid: str) -> int:
        uid_str = str(uid)
        acc = self.accounts.get(uid_str)
        if not acc:
            mapped = self.game_to_auth_id.get(uid_str) or self.auth_to_game_id.get(uid_str)
            if mapped and mapped in self.accounts:
                acc = self.accounts[mapped]
        if acc:
            return int(acc.get("level", 1) or 1)
        return 1

    def get_account_mode(self, uid: str) -> str:
        lvl = self.get_account_level(uid)
        return "BR" if lvl < 3 else "LONE_WOLF"

    def update_status(self, uid: str, status: str, active_matches: Optional[int] = None):
        uid_str = str(uid)
        if uid_str in self.accounts:
            self.accounts[uid_str]["status"] = status
            if active_matches is not None:
                self.accounts[uid_str]["active_matches"] = active_matches
            self.accounts[uid_str]["last_updated"] = time.strftime("%H:%M:%S")


    def record_relogin(self, uid: str, state: str, message: str = ""):
        """Dashboard ke liye re-login history. state: start | ok | fail"""
        uid_str = str(uid)
        ev = self.relogin_events.setdefault(uid_str, {
            "count": 0, "ok": 0, "fail": 0, "last_time": None, "last_status": "-", "last_message": ""
        })
        ev["last_time"] = time.strftime("%H:%M:%S")
        ev["last_message"] = message
        if state == "start":
            ev["count"] += 1
            ev["last_status"] = "IN_PROGRESS"
        elif state == "ok":
            ev["ok"] += 1
            ev["last_status"] = "OK"
        else:
            ev["fail"] += 1
            ev["last_status"] = "FAILED"

    def increment_match_started(self):
        """Track total matches STARTED (not completed)"""
        self.total_matches_started += 1

    def increment_match(self, uid: str):
        uid_str = str(uid)
        self.total_matches += 1
        if uid_str in self.accounts:
            self.accounts[uid_str]["matches_played"] += 1
            self.accounts[uid_str]["last_match_time"] = time.strftime("%H:%M:%S")
            self.accounts[uid_str]["last_updated"] = time.strftime("%H:%M:%S")
            self.log(f"⚔ Match #{self.accounts[uid_str]['matches_played']} finished for {self.accounts[uid_str]['nickname']} ({uid_str})", "info", uid_str)

    def recalc_totals(self):
        self.total_gained_exp = sum(acc.get("gained_exp", 0) for acc in self.accounts.values())


bot_state = BotState()

FALLBACK_INDEX_HTML = """<!DOCTYPE html>
<html>
<head><title>TEAM RBC Bot Dashboard</title></head>
<body style="background:#0a0a12;color:#fff;font-family:sans-serif;text-align:center;padding:50px;">
<h1>TEAM RBC BOT RUNNING</h1>
<p>Dashboard interface loaded successfully.</p>
</body>
</html>"""

async def handle_index(request: web.Request) -> web.Response:
    content = FALLBACK_INDEX_HTML
    if os.path.exists(TEMPLATE_PATH):
        try:
            with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            pass
    return web.Response(text=content, content_type="text/html", charset="utf-8")

# ==================== GUILD SETUP / JOIN API ENDPOINTS ====================
async def _load_accounts_for_join():
    accounts_file = "accounts.json"
    try:
        with open(accounts_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return [
            {"uid": str(a.get("uid", "")).strip(), "password": str(a.get("password", "")).strip()}
            for a in data
            if str(a.get("uid", "")).strip() and str(a.get("password", "")).strip()
        ]
    except Exception:
        return []


def _first_present(data: dict, *keys, default=None):
    if not isinstance(data, dict):
        return default
    for key in keys:
        value = data.get(key)
        if value is not None and value != "":
            return value
    return default


def _unwrap_guild_info(payload):
    """Unwrap common public guild API response envelopes."""
    if not isinstance(payload, dict):
        return {}
    data = payload
    api_response = payload.get("api_response")
    if isinstance(api_response, dict):
        nested = api_response.get("clan_basic_info") or api_response.get("guild") or api_response
        if isinstance(nested, dict):
            data = nested
    else:
        for key in ("data", "result", "guild", "clan_basic_info"):
            nested = data.get(key)
            if isinstance(nested, dict):
                data = nested
    return data


def _save_guild_config(guild_id: str, region: str, guild_data: dict):
    data = _unwrap_guild_info(guild_data)
    payload = {
        "guild_id": str(guild_id),
        "region": str(region).upper(),
        "guild_name": _first_present(data, "guild_name", "GuildName", "clan_name", "ClanName", "name", "special_code", default="N/H"),
        "guild_region": _first_present(data, "region", "GuildRegion", default=str(region).upper()),
        "max_members": _first_present(data, "max_members", "MaxMembers", "maxMembers"),
        "guild_level": _first_present(data, "guild_level", "GuildLevel", "clan_level", "ClanLevel", "level", "rank"),
        "current_members": _first_present(data, "current_members", "CurrentMembers", "MemberNum", "MemberCount", "total_members", "TotalMembers", "members_count", "member_count"),
        "glory": _first_present(data, "glory", "GuildGlory", "GuildExp", "TotalGuildExp", "Total guild xp", "total_guild_xp", "xp", "exp"),
        "remaining_to_next_level": _first_present(data, "remaining_to_next_level", "RemainingToNextLevel", "NextLevelRemaining", "next_level_remaining"),
        "next_level_glory": _first_present(data, "next_level_glory", "NextLevelGlory", "NextLevelExp", "next_level_exp", "NextGuildExp"),
        "details": {str(k): v for k, v in list(data.items())[:40] if isinstance(v, (str, int, float, bool))},
        "updated_at": int(time.time()),
    }
    try:
        _write_json_atomic(GUILD_CONFIG_FILE, payload)
    except Exception:
        pass
    bot_state.guild_config = payload
    return payload

async def _fetch_external_guild_info(guild_id: str, region: str):
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        r = await client.get(GUILD_INFO_API, params={"guild_id": guild_id, "region": region})
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
        if r.status_code >= 400:
            raise RuntimeError(f"Guild info API HTTP {r.status_code}: {data}")
        if not isinstance(data, dict):
            raise RuntimeError("Guild info API returned an unexpected response")
        if data.get("status") == "error" or data.get("success") is False:
            raise RuntimeError(str(data.get("message") or data.get("error") or "Guild info API returned an error"))
        return data


async def _send_external_join(guild_id: str, uid: str, password: str):
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        r = await client.get(
            GUILD_JOIN_API,
            params={"guild_uid": guild_id, "uid": uid, "password": password},
        )
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
        return r.status_code, data


async def _run_automation(guild_id: str, region: str, total: int, threads: int, fresh_pool: bool):
    """Generate accounts -> fetch guild -> send join requests -> start Glory."""
    bot_state.automation.update({
        "running": True, "stage": "generating", "target": total,
        "created": 0, "joined": 0, "failed": 0,
        "message": "Generating accounts…", "started_at": time.time()
    })
    _archive_accounts()      # fresh pool se pehle purane accounts ka archive (khona nahi)
    try:
        # Keep the event loop responsive while the generator uses its own workers.
        if total > 0:
            if account_generator is None:
                raise RuntimeError("gen.py is not included. Use the existing accounts.json flow or add gen.py before requesting account generation.")
            result = await asyncio.to_thread(account_generator.generate_accounts, total, threads, fresh_pool)
            bot_state.automation["created"] = int(result.get("created", 0))
            bot_state.automation["message"] = f"Generated {result.get('created', 0)}/{total} account(s)"
            if int(result.get("created", 0)) < total:
                raise RuntimeError(f"Generator created {result.get('created', 0)}/{total} accounts")
        else:
            bot_state.automation["message"] = "Using existing accounts.json"

        bot_state.automation["stage"] = "guild"
        bot_state.automation["message"] = "Loading guild information…"
        external_info = await _fetch_external_guild_info(guild_id, region)
        guild_data = _unwrap_guild_info(external_info)
        config = _save_guild_config(guild_id, region, guild_data)
        bot_state.log(
            f"Guild loaded: {config.get('guild_name', 'N/H')} | ID {guild_id} | Region {region} | Level {config.get('guild_level', 'N/H')}",
            "success",
        )

        bot_state.automation["stage"] = "joining"
        bot_state.automation["message"] = "Sending join requests…"
        accounts = await _load_accounts_for_join()
        if not accounts:
            raise RuntimeError("No valid UID/password entries found in accounts.json")

        join_results = []
        for account in accounts:
            uid = account["uid"]
            try:
                http_status, result = await _send_external_join(guild_id, uid, account["password"])
                join_payload = result.get("data", result) if isinstance(result, dict) else {}
                success = bool(isinstance(join_payload, dict) and join_payload.get("success") is True)
                message = join_payload.get("message", "") if isinstance(join_payload, dict) else ""
                label = "Join Request Sended" if success else "Join Request Failed"
                bot_state.log(f"UID {uid}: {label}" + (f" | {message}" if message else ""), "success" if success else "error", uid)
                join_results.append({"uid": uid, "success": success, "status": label, "http_status": http_status, "response": result})
                if success:
                    bot_state.automation["joined"] += 1
                else:
                    bot_state.automation["failed"] += 1
            except Exception as e:
                bot_state.log(f"UID {uid}: Join Request Failed | {e}", "error", uid)
                join_results.append({"uid": uid, "success": False, "status": "Join Request Failed", "error": str(e)})
                bot_state.automation["failed"] += 1
            await asyncio.sleep(2)

        bot_state.automation["stage"] = "starting"
        bot_state.automation["message"] = "Starting AjayXGlory…"
        if "on_glory_start" not in bot_state.refresh_callbacks:
            raise RuntimeError("Glory start callback is not ready yet")
        await bot_state.refresh_callbacks["on_glory_start"]()
        bot_state.glory_started = True
        bot_state.setup_complete = True
        bot_state.log(f"AjayXGlory started | {len(accounts)} account(s)", "success")
        bot_state.automation.update({"running": False, "stage": "done", "message": "Generation → Join → Glory complete"})
    except Exception as e:
        bot_state.automation.update({"running": False, "stage": "error", "message": str(e)})
        bot_state.log(f"Automation failed: {e}", "error")


async def handle_api_start(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        body = {}
    if bot_state.automation.get("running"):
        return web.json_response({"status": "busy", "automation": bot_state.automation}, status=409)
    guild_id = str(body.get("guild_id", "")).strip()
    region = str(body.get("region", "IND")).strip().upper() or "IND"
    try:
        total = max(1, min(500, int(body.get("total_accounts", 1))))
        threads = max(1, min(30, int(body.get("threads", min(5, total)))))
    except Exception:
        return web.json_response({"status": "error", "error": "Invalid account/thread count"}, status=400)
    fresh_pool = bool(body.get("fresh_pool", True))
    if not guild_id:
        return web.json_response({"status": "error", "error": "Guild ID is required"}, status=400)
    bot_state.automation_task = asyncio.create_task(_run_automation(guild_id, region, total, threads, fresh_pool))
    return web.json_response({"status": "started", "automation": bot_state.automation})


async def handle_api_automation(request: web.Request) -> web.Response:
    return web.json_response({"status": "success", "automation": bot_state.automation, "guild": bot_state.guild_config, "glory_started": bot_state.glory_started, "guild_live": bot_state.guild_live})


async def handle_api_setup(request: web.Request) -> web.Response:
    """Backward-compatible setup endpoint: join existing accounts and start Glory."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    guild_id = str(body.get("guild_id", "")).strip()
    region = str(body.get("region", "IND")).strip().upper() or "IND"
    if not guild_id:
        return web.json_response({"status": "error", "error": "Guild ID is required"}, status=400)
    if bot_state.automation.get("running"):
        return web.json_response({"status": "busy", "automation": bot_state.automation}, status=409)
    asyncio.create_task(_run_automation(guild_id, region, 0, 1, False))
    return web.json_response({"status": "started", "message": "Automation started. Use /api/automation for progress."})


async def handle_api_guild_config(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "success",
        "setup_complete": bot_state.setup_complete,
        "glory_started": bot_state.glory_started,
        "guild": bot_state.guild_config,
    })


# ==================== GUILD INFO API ENDPOINT (AIOHTTP) ====================
GUILD_CACHE_FILE = "guild_exp_cache.json"

def load_guild_cache():
    if os.path.exists(GUILD_CACHE_FILE):
        try:
            with open(GUILD_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_guild_cache(cache_data):
    try:
        with open(GUILD_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=4)
    except Exception:
        pass

def get_persisted_baseline_xp(clan_id, current_xp):
    cache = load_guild_cache()
    clan_key = str(clan_id)
    
    if clan_key not in cache or "old_xp" not in cache[clan_key]:
        cache[clan_key] = {
            "old_xp": current_xp,
            "live_xp": current_xp,
            "gained_exp": 0
        }
        save_guild_cache(cache)
        return current_xp
    
    return int(cache[clan_key]["old_xp"])

async def handle_api_guild_info(request: web.Request) -> web.Response:
    try:
        guild_id = str(request.query.get("guild_id", "")).strip()
        region = str(request.query.get("region", "IND")).strip().upper()
        if not guild_id:
            return web.json_response({"status": "error", "error": "guild_id is required"}, status=400)

        # Always fetch a fresh preview; cached guild data may be stale after a rename/level change.
        data = await _fetch_external_guild_info(guild_id, region)
        guild_data = _unwrap_guild_info(data)
        return web.json_response({"status": "success", **guild_data})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)}, status=502)


async def _join_new_account_to_selected_guild(uid: str, password: str):
    """Send a join request for a newly-added account to the currently selected guild."""
    guild = dict(bot_state.guild_config or {})
    guild_id = str(guild.get("guild_id") or "").strip()
    region = str(guild.get("region") or "IND").upper()
    if not guild_id:
        return
    try:
        status, payload = await _send_external_join(guild_id, uid, password)
        result = payload.get("data", payload) if isinstance(payload, dict) else {}
        success = bool(isinstance(result, dict) and result.get("success") is True)
        message = result.get("message", "") if isinstance(result, dict) else str(payload)
        label = "Join request sent" if success else "Join request failed"
        bot_state.log(f"UID {uid}: {label}" + (f" | {message}" if message else f" | HTTP {status}"),
                      "success" if success else "error", uid)
    except Exception as exc:
        bot_state.log(f"UID {uid}: Guild join request failed | {exc}", "error", uid)


async def handle_upload_accounts_json(request: web.Request) -> web.Response:
    """Validate and merge an uploaded accounts.json without exposing its contents."""
    try:
        reader = await request.multipart()
        part = await reader.next()
        if part is None or part.name != "file":
            return web.json_response({"status": "error", "error": "Choose an accounts.json file."}, status=400)
        filename = os.path.basename(part.filename or "")
        if filename.lower() != "accounts.json":
            return web.json_response({"status": "error", "error": "File must be named accounts.json."}, status=400)
        raw = await part.read(decode=False)
        if len(raw) > 2 * 1024 * 1024:
            return web.json_response({"status": "error", "error": "File is too large (maximum 2 MB)."}, status=413)
        try:
            uploaded = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return web.json_response({"status": "error", "error": "Invalid JSON file."}, status=400)
        if not isinstance(uploaded, list):
            return web.json_response({"status": "error", "error": "JSON must contain a list of account objects."}, status=400)

        clean = []
        for item in uploaded:
            if not isinstance(item, dict):
                return web.json_response({"status": "error", "error": "Every account must be a JSON object."}, status=400)
            uid, password, token = str(item.get("uid", "")).strip(), str(item.get("password", "")).strip(), str(item.get("token", "")).strip()
            if uid and password:
                clean.append({"uid": uid, "password": password})
            elif token:
                clean.append({"token": token})
            else:
                return web.json_response({"status": "error", "error": "Each account needs UID + password, or a token."}, status=400)
        if not clean:
            return web.json_response({"status": "error", "error": "No accounts found in the JSON file."}, status=400)

        accounts_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "accounts.json")
        existing = _read_json_list(accounts_file)
        by_key = {}
        for acc in existing:
            if isinstance(acc, dict):
                key = ("uid", str(acc.get("uid", "")).strip()) if acc.get("uid") else ("token", str(acc.get("token", "")).strip())
                if key[1]: by_key[key] = acc
        added = 0
        for acc in clean:
            key = ("uid", acc["uid"]) if "uid" in acc else ("token", acc["token"])
            if key not in by_key:
                by_key[key] = acc
                added += 1
        merged = list(by_key.values())
        _write_json_atomic(accounts_file, merged)
        _archive_accounts()

        callback = bot_state.refresh_callbacks.get("on_account_added")
        if callback:
            async def start_imported_accounts():
                for acc in clean:
                    try:
                        await callback(acc)
                    except Exception as exc:
                        bot_state.log(f"Imported account could not be started: {exc}", "warning")
                    await asyncio.sleep(0.25)
            asyncio.create_task(start_imported_accounts())
        bot_state.log(f"accounts.json imported: {added} new account(s)", "success")
        return web.json_response({"status": "ok", "added": added, "total": len(merged), "message": f"Import complete: {added} new account(s) added."})
    except Exception as exc:
        return web.json_response({"status": "error", "error": str(exc)}, status=500)


async def handle_delete_accounts_json(request: web.Request) -> web.Response:
    """Delete the accounts.json file only; leave archived accounts untouched."""
    try:
        accounts_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "accounts.json")
        if not os.path.isfile(accounts_file):
            return web.json_response({"status": "ok", "message": "accounts.json does not exist."})
        os.remove(accounts_file)
        bot_state.log("accounts.json file deleted from dashboard", "warning")
        return web.json_response({"status": "ok", "message": "accounts.json deleted. The account archive was not changed."})
    except Exception as exc:
        return web.json_response({"status": "error", "error": str(exc)}, status=500)


async def handle_add_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        accounts_file = "accounts.json"
        existing = []
        if os.path.exists(accounts_file):
            try:
                with open(accounts_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []

        if "uid" in data and "password" in data:
            uid = str(data["uid"]).strip()
            pwd = str(data["password"]).strip()
            if not uid or not pwd:
                return web.json_response({"status": "error", "error": "UID and Password are required"})

            # Cancel previous worker if already running for this UID
            if uid in bot_state.account_workers:
                try:
                    bot_state.account_workers[uid].cancel()
                except Exception:
                    pass
                bot_state.account_workers.pop(uid, None)

            existing = [acc for acc in existing if str(acc.get("uid", "")) != uid]
            existing.append({"uid": uid, "password": pwd})
            identifier = uid

        elif "token" in data:
            token = str(data["token"]).strip()
            if not token:
                return web.json_response({"status": "error", "error": "Token is required"})

            # Cancel worker if token prefix matches
            tok_key = token[:16]
            for k in list(bot_state.account_workers.keys()):
                if k == tok_key or k.startswith(tok_key[:10]) or tok_key.startswith(k[:10]):
                    try:
                        bot_state.account_workers[k].cancel()
                    except Exception:
                        pass
                    bot_state.account_workers.pop(k, None)

            existing = [acc for acc in existing if acc.get("token", "") != token]
            existing.append({"token": token})
            identifier = f"Token_{token[:8]}..."
        else:
            return web.json_response({"status": "error", "error": "Invalid payload"})

        with open(accounts_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)

        bot_state.log(f"New account added to rotation: {identifier}", "success")
        _archive_accounts()
        
        # A newly-added UID/password account is also sent to the selected guild.
        if "uid" in data and "password" in data and bot_state.guild_config.get("guild_id"):
            asyncio.create_task(_join_new_account_to_selected_guild(uid, pwd))

        # Trigger dynamic worker launch in the game worker.
        if "on_account_added" in bot_state.refresh_callbacks:
            asyncio.create_task(bot_state.refresh_callbacks["on_account_added"](data))

        return web.json_response({
            "status": "ok",
            "message": "Account added. Guild join request queued." if ("uid" in data and bot_state.guild_config.get("guild_id")) else "Account added."
        })
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_delete_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        req_uid = str(data.get("uid", "")).strip()
        req_auth_uid = str(data.get("auth_uid", "")).strip()
        if not req_uid and not req_auth_uid:
            return web.json_response({"status": "error", "error": "UID is required"})

        # Collect ALL possible candidate identifiers for this account
        candidate_ids = set()
        if req_uid:
            candidate_ids.add(req_uid)
        if req_auth_uid:
            candidate_ids.add(req_auth_uid)

        # Check game_to_auth and auth_to_game mappings
        for cid in list(candidate_ids):
            if cid in bot_state.game_to_auth_id:
                candidate_ids.add(str(bot_state.game_to_auth_id[cid]))
            if cid in bot_state.auth_to_game_id:
                candidate_ids.add(str(bot_state.auth_to_game_id[cid]))

        # Inspect bot_state.accounts
        target_tokens = set()
        for cid in list(candidate_ids):
            acc_info = bot_state.accounts.get(cid, {})
            if acc_info:
                if acc_info.get("auth_uid"):
                    candidate_ids.add(str(acc_info["auth_uid"]))
                if acc_info.get("uid"):
                    candidate_ids.add(str(acc_info["uid"]))
                t = acc_info.get("token") or acc_info.get("access_token")
                if t:
                    target_tokens.add(str(t))

        # Inspect bot_state.account_credentials
        for cid in list(candidate_ids):
            creds = bot_state.account_credentials.get(cid, {})
            if creds:
                if creds.get("auth_uid"):
                    candidate_ids.add(str(creds["auth_uid"]))
                if creds.get("account_id"):
                    candidate_ids.add(str(creds["account_id"]))
                t = creds.get("token") or creds.get("access_token") or creds.get("auth_token")
                if t:
                    target_tokens.add(str(t))

        # Also clean token_cache.json if entries match
        token_cache_file = "token_cache.json"
        if os.path.exists(token_cache_file):
            try:
                with open(token_cache_file, "r", encoding="utf-8") as f:
                    tcache = json.load(f)
                dirty_cache = False
                for k, v in list(tcache.items()):
                    k_str = str(k)
                    v_acc_id = str(v.get("account_id", ""))
                    v_auth_uid = str(v.get("auth_uid", ""))
                    if k_str in candidate_ids or v_acc_id in candidate_ids or v_auth_uid in candidate_ids:
                        candidate_ids.add(k_str)
                        if v_acc_id:
                            candidate_ids.add(v_acc_id)
                        if v_auth_uid:
                            candidate_ids.add(v_auth_uid)
                        del tcache[k]
                        dirty_cache = True
                if dirty_cache:
                    with open(token_cache_file, "w", encoding="utf-8") as f:
                        json.dump(tcache, f, indent=2)
            except Exception:
                pass

        # Remove from accounts.json
        accounts_file = "accounts.json"
        if os.path.exists(accounts_file):
            try:
                with open(accounts_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                new_existing = []
                for acc in existing:
                    acc_uid = str(acc.get("uid", "")).strip()
                    acc_tok = str(acc.get("token", "")).strip()
                    is_match = False
                    if acc_uid and acc_uid in candidate_ids:
                        is_match = True
                    if acc_tok and (acc_tok in candidate_ids or acc_tok in target_tokens):
                        is_match = True
                    for tok in target_tokens:
                        if acc_tok and (acc_tok.startswith(tok[:16]) or tok.startswith(acc_tok[:16])):
                            is_match = True
                    if not is_match:
                        new_existing.append(acc)

                with open(accounts_file, "w", encoding="utf-8") as f:
                    json.dump(new_existing, f, indent=2)
            except Exception:
                pass

        # Remove matching devices from devices.json
        devices_file = "devices.json"
        if os.path.exists(devices_file):
            try:
                with open(devices_file, "r", encoding="utf-8") as f:
                    devices_data = json.load(f)
                dirty_devices = False
                for dev_k in list(devices_data.keys()):
                    dev_k_str = str(dev_k)
                    if dev_k_str in candidate_ids:
                        del devices_data[dev_k]
                        dirty_devices = True
                    else:
                        for tok in target_tokens:
                            if dev_k_str == tok[:16] or tok.startswith(dev_k_str):
                                del devices_data[dev_k]
                                dirty_devices = True
                                break
                if dirty_devices:
                    with open(devices_file, "w", encoding="utf-8") as f:
                        json.dump(devices_data, f, indent=4)
            except Exception:
                pass

        # Remove from in-memory bot_state.accounts & credentials
        for cid in candidate_ids:
            bot_state.accounts.pop(cid, None)
            bot_state.account_credentials.pop(cid, None)
            bot_state.auth_to_game_id.pop(cid, None)
            bot_state.game_to_auth_id.pop(cid, None)
            bot_state.account_token_map.pop(cid, None)

        # Cancel matching worker tasks
        cancelled_keys = []
        for k, worker in list(bot_state.account_workers.items()):
            k_str = str(k)
            should_cancel = False
            if k_str in candidate_ids:
                should_cancel = True
            for tok in target_tokens:
                if k_str == tok[:16] or tok.startswith(k_str[:10]):
                    should_cancel = True
            if should_cancel:
                try:
                    worker.cancel()
                except Exception:
                    pass
                cancelled_keys.append(k)

        for k in cancelled_keys:
            bot_state.account_workers.pop(k, None)

        for cid in candidate_ids:
            bot_state.close_writers_for_account(cid)

        # Trigger on_account_deleted callback in Main.py if registered
        if "on_account_deleted" in bot_state.refresh_callbacks:
            try:
                asyncio.create_task(bot_state.refresh_callbacks["on_account_deleted"](list(candidate_ids)))
            except Exception:
                pass

        target_repr = req_uid or req_auth_uid
        bot_state.log(f"Account {target_repr} completely deleted from system and stopped.", "warning", target_repr)
        bot_state.recalc_totals()
        return web.json_response({"status": "ok", "deleted": list(candidate_ids)})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_refresh_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        uid = str(data.get("uid", "")).strip()
        if "on_refresh_account" in bot_state.refresh_callbacks:
            asyncio.create_task(bot_state.refresh_callbacks["on_refresh_account"](uid))
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_restart_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        uid = str(data.get("uid", "")).strip()
        if "on_restart_account" in bot_state.refresh_callbacks:
            asyncio.create_task(bot_state.refresh_callbacks["on_restart_account"](uid))
        elif "on_refresh_account" in bot_state.refresh_callbacks:
            asyncio.create_task(bot_state.refresh_callbacks["on_refresh_account"](uid))
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_clear_logs(request: web.Request) -> web.Response:
    bot_state.logs.clear()
    return web.json_response({"status": "ok"})


async def handle_toggle_pause(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        uid = str(data.get("uid", "")).strip()
        if not uid:
            return web.json_response({"status": "error", "error": "UID is required"})
        is_paused = bot_state.toggle_pause(uid)
        return web.json_response({"status": "ok", "is_paused": is_paused})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_toggle_pause_all(request: web.Request) -> web.Response:
    try:
        paused_state = bot_state.toggle_pause_all()
        return web.json_response({"status": "ok", "all_paused": paused_state})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})

async def handle_api_logs(request: web.Request) -> web.Response:
    formatted_logs = []
    for entry in bot_state.logs[-80:]:
        if isinstance(entry, dict):
            t = entry.get("time", "")
            msg = entry.get("message", "")
            level = entry.get("level", "info")
            color = "#34d399" if level == "success" else ("#f87171" if level == "warning" or level == "error" else "#38bdf8")
            formatted_logs.append(f'<span style="color:{color}">[{t}] {msg}</span>')
        else:
            formatted_logs.append(str(entry))
    return web.json_response({"logs": formatted_logs}, status=200)


# ==================== LIVE GUILD (glory / gain / members) ====================
GUILD_LIVE_INTERVAL = 30   # seconds - game server se guild ka live data kitni der mein lena hai

def _parse_clan_members(raw_hex):
    """Decode guild details and merge both roster fields without duplicates."""
    out = {"members": [], "members_online": None, "total_members": None, "leader_uid": None,
           "notice": "", "name": None, "level": None}
    try:
        resp = data_pb2.response()
        resp.ParseFromString(bytes.fromhex(raw_hex))
        if not resp.HasField("guild_details"):
            return out
        gd = resp.guild_details
        out.update(name=gd.name or None, level=int(gd.level) if gd.level else None,
                   members_online=int(gd.members_online) if gd.members_online else None,
                   total_members=int(gd.total_members) if gd.total_members else None,
                   leader_uid=str(gd.leader_uid) if gd.leader_uid else None, notice=gd.notice or "")
        seen = set()
        for member in list(gd.member_list) + list(gd.members):
            uid = str(member.uid)
            if not uid or uid in seen:
                continue
            seen.add(uid)
            out["members"].append({
                "uid": uid, "name": member.nickname or f"Player_{uid[-6:]}",
                "level": int(member.level) if member.level else None,
                "role": int(member.role) if member.role else None,
                "score": int(member.score) if member.score else 0,
                "last_active": int(member.last_active) if member.last_active else None,
                "avatar_id": int(member.avatar_id) if member.avatar_id else None,
                "banner_id": int(member.banner_id) if member.banner_id else None,
                "is_leader": bool(gd.leader_uid) and uid == str(gd.leader_uid),
                "is_ours": uid in bot_state.accounts,
                "our_status": (bot_state.accounts.get(uid) or {}).get("status"),
            })
        out["members"].sort(key=lambda x: (not x["is_leader"], -int(x["score"] or 0)))
    except Exception as exc:
        out["parse_error"] = str(exc)
    return out

async def _guild_live_loop():
    """Har GUILD_LIVE_INTERVAL second mein guild ka live glory + members laata hai (sirf padhta hai, 1 request)."""
    session_base = {}
    history = []
    last_gid = None
    last_err = None
    while True:
        try:
            if not bot_state.guild_config and os.path.exists(GUILD_CONFIG_FILE):
                try:
                    with open(GUILD_CONFIG_FILE, "r", encoding="utf-8") as f:
                        bot_state.guild_config = json.load(f)
                except Exception:
                    pass
            gc = bot_state.guild_config or {}
            gid = str(gc.get("guild_id") or "").strip()
            region = str(gc.get("region") or gc.get("guild_region") or "IND").upper()
            creds = {}
            for _k, ad in list(bot_state.account_credentials.items()):
                if isinstance(ad, dict) and ad.get("token") and ad.get("account_id"):
                    creds.setdefault(str(ad["account_id"]), {"token": ad["token"]})
                if len(creds) >= 6:
                    break
            if gid and not creds:
                bot_state.guild_live = {
                    "ok": False, "error": "Waiting for an account to finish login",
                    "guild_id": gid, "region": region, "members": [],
                    "updated_at": int(time.time()), "interval": GUILD_LIVE_INTERVAL,
                }
            if gid and creds:
                if gid != last_gid:
                    history, last_gid = [], gid
                data = await asyncio.to_thread(fetch_single_clan, gid, region, creds)
                if not isinstance(data, dict) or data.get("error"):
                    raise RuntimeError((data or {}).get("error", "guild info nahi mili") if isinstance(data, dict) else "guild info nahi mili")
                glory = int(data.get("glory", data.get("xp", 0)) or 0)
                if glory < 0:
                    raise RuntimeError("Game response mein invalid glory value mili")
                extra = _parse_clan_members(data.get("raw_response_bytes", ""))
                now = time.time()
                base_total = get_persisted_baseline_xp(gid, glory)
                if gid not in session_base:
                    session_base[gid] = (now, glory)
                s_t, s_g = session_base[gid]
                gained_session = glory - s_g
                per_hour = int(gained_session / ((now - s_t) / 3600)) if now - s_t >= 60 else 0
                try:
                    cache = load_guild_cache()
                    e = cache.get(str(gid), {})
                    e["live_xp"] = glory
                    e["gained_exp"] = max(0, glory - int(e.get("old_xp", glory)))
                    cache[str(gid)] = e
                    save_guild_cache(cache)
                except Exception:
                    pass
                history.append([int(now), glory])
                history = history[-90:]
                bot_state.guild_live = {
                    "ok": True, "error": None, "guild_id": gid, "region": region,
                    "glory": glory, "baseline": base_total,
                    "gained_total": max(0, glory - base_total), "gained_session": max(0, gained_session), "per_hour": max(0, per_hour),
                    "name": extra["name"] or gc.get("guild_name"),
                    "level": extra["level"] or data.get("clan_level") or gc.get("guild_level"),
                    "members_online": extra["members_online"], "total_members": extra["total_members"] or gc.get("current_members"),
                    "leader_uid": extra["leader_uid"], "notice": extra["notice"] or data.get("welcome_message", ""),
                    "members": extra["members"], "history": history,
                    "updated_at": int(now), "interval": GUILD_LIVE_INTERVAL,
                }
                last_err = None
        except asyncio.CancelledError:
            raise
        except Exception as e:
            msg = str(e)
            prev = dict(bot_state.guild_live or {})
            prev.update(ok=False, error=msg, interval=GUILD_LIVE_INTERVAL)
            bot_state.guild_live = prev
            if msg != last_err:          # same error baar baar log nahi karna
                last_err = msg
                bot_state.log(f"[GUILD LIVE] {msg}", "warning")
        await asyncio.sleep(GUILD_LIVE_INTERVAL)


async def handle_api_guild_refresh(request: web.Request) -> web.Response:
    """Force a fresh guild info/glory/member read for the currently selected guild."""
    try:
        guild_id = str(request.query.get("guild_id") or bot_state.guild_config.get("guild_id") or "").strip()
        region = str(request.query.get("region") or bot_state.guild_config.get("region") or "IND").upper()
        if not guild_id:
            return web.json_response({"status": "error", "error": "Select a Guild ID first"}, status=400)

        external = await _fetch_external_guild_info(guild_id, region)
        basic = _unwrap_guild_info(external)
        config = _save_guild_config(guild_id, region, basic)

        creds = {}
        for _, account in list(bot_state.account_credentials.items()):
            if isinstance(account, dict) and account.get("token") and account.get("account_id"):
                creds.setdefault(str(account["account_id"]), {"token": account["token"]})
            if len(creds) >= 6:
                break
        live = dict(bot_state.guild_live or {})
        if str(live.get("guild_id") or "") != guild_id:
            live = {}
        if not creds:
            live = {"ok": False, "error": "Waiting for an account to finish login",
                    "guild_id": guild_id, "region": region, "members": [],
                    "updated_at": int(time.time()), "interval": GUILD_LIVE_INTERVAL}
        if creds:
            raw = await asyncio.to_thread(fetch_single_clan, guild_id, region, creds)
            if isinstance(raw, dict) and not raw.get("error"):
                glory = int(raw.get("glory", raw.get("xp", 0)) or 0)
                baseline = get_persisted_baseline_xp(guild_id, glory)
                extra = _parse_clan_members(raw.get("raw_response_bytes", ""))
                live.update({
                    "ok": True, "error": None, "guild_id": guild_id, "region": region,
                    "glory": glory, "baseline": baseline, "gained_total": max(0, glory-baseline),
                    "name": extra.get("name") or config.get("guild_name"),
                    "level": extra.get("level") or raw.get("clan_level") or config.get("guild_level"),
                    "members_online": extra.get("members_online"),
                    "total_members": extra.get("total_members") or config.get("current_members"),
                    "leader_uid": extra.get("leader_uid"), "members": extra.get("members", []),
                    "updated_at": int(time.time()), "interval": GUILD_LIVE_INTERVAL
                })
                bot_state.guild_live = live
        return web.json_response({"status": "success", "guild": config, "guild_live": bot_state.guild_live})
    except Exception as exc:
        bot_state.log(f"Guild refresh failed: {exc}", "warning")
        return web.json_response({"status": "error", "error": str(exc),
                                  "guild": bot_state.guild_config, "guild_live": bot_state.guild_live}, status=502)


# ==================== START WEB DASHBOARD ====================

async def start_web_dashboard(host: str = "0.0.0.0", port: int = 5000):
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_post("/api/setup", handle_api_setup)
    app.router.add_post("/api/start", handle_api_start)
    app.router.add_get("/api/automation", handle_api_automation)
    app.router.add_get("/api/guild-config", handle_api_guild_config)
    app.router.add_post("/api/clanjoin", handle_api_setup)
    app.router.add_get("/api/guildinfo", handle_api_guild_info)
    app.router.add_get("/api/guild/refresh", handle_api_guild_refresh)
    app.router.add_get("/api/stats", handle_get_stats)
    app.router.add_get("/api/logs", handle_api_logs)
    app.router.add_post("/api/account/add", handle_add_account)
    app.router.add_post("/api/accounts/upload", handle_upload_accounts_json)
    app.router.add_post("/api/accounts/delete-file", handle_delete_accounts_json)
    app.router.add_post("/api/accounts/old/activate", handle_activate_old)
    app.router.add_post("/api/account/delete", handle_delete_account)
    app.router.add_post("/api/account/refresh", handle_refresh_account)
    app.router.add_post("/api/account/restart", handle_restart_account)
    app.router.add_post("/api/account/pause", handle_toggle_pause)
    app.router.add_post("/api/account/pause_all", handle_toggle_pause_all)
    app.router.add_post("/api/logs/clear", handle_clear_logs)    

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    _archive_accounts()      # dashboard start par bhi: jo accounts accounts.json mein hain unka archive
    try:
        asyncio.create_task(_guild_live_loop())
    except Exception:
        pass
    return runner
