import time, json, redis
from typing import Tuple, Optional, Dict

def connect(url: str) -> redis.Redis:
    r = redis.Redis.from_url(url)
    for i in range(10):
        try:
            r.ping(); break
        except redis.exceptions.ConnectionError:
            time.sleep(2)
    return r

def now_ms() -> int: return int(time.time() * 1000)
def day_key() -> str: return time.strftime("%Y%m%d", time.gmtime())

# idempotency
def idempotency_check(r: redis.Redis, tv_id: str, ttl: int) -> bool:
    if not tv_id: raise ValueError("missing id")
    ok = r.setnx(f"idemp:{tv_id}", str(now_ms()))
    if ok: r.expire(f"idemp:{tv_id}", ttl)
    return bool(ok)

# streak/cooldown
def get_loss_streak(r: redis.Redis, strategy: str) -> int:
    v = r.get(f"streak:{strategy}")
    return int(v) if v else 0

def set_loss_streak(r: redis.Redis, strategy: str, v: int):
    r.set(f"streak:{strategy}", str(int(v)), ex=7*24*3600)

def is_cooldown(r: redis.Redis, strategy: str) -> Tuple[bool, Optional[int]]:
    v = r.get(f"cooldown_until:{strategy}")
    if not v: return False, None
    until_ms = int(v); return (now_ms() < until_ms, until_ms)

def start_cooldown(r: redis.Redis, strategy: str, minutes: int):
    until = now_ms() + int(minutes*60*1000)
    r.set(f"cooldown_until:{strategy}", str(until), ex=48*3600)

# daily pnl & dd
def update_daily_pnl(r: redis.Redis, pnl_usdt: float):
    dk = day_key()
    key = f"day:pnltotal:{dk}"
    cur = float(r.get(key) or 0.0)
    cur += float(pnl_usdt)
    r.set(key, str(cur), ex=3*24*3600)
    # peak & dd
    pkey = f"day:peak:{dk}"
    peak = float(r.get(pkey) or 0.0)
    if cur > peak: peak = cur
    r.set(pkey, str(peak), ex=3*24*3600)
    dd = cur - peak
    r.set(f"day:dd:{dk}", str(dd), ex=3*24*3600)
    return cur, peak, dd

def daily_dd_blocked(r: redis.Redis, limit_usdt: float):
    if limit_usdt <= 0: return (False, {})
    dk = day_key()
    cur = float(r.get(f"day:pnltotal:{dk}") or 0.0)
    peak = float(r.get(f"day:peak:{dk}") or 0.0)
    dd = cur - peak
    return (dd <= -abs(limit_usdt), {"day_pnl":cur, "day_peak":peak, "day_dd":dd})

# open entry snapshot (for simple realized pnl)
def save_open_entry(r: redis.Redis, strategy: str, side: str, entry_px: float, amount: float):
    rec = {"strategy": strategy, "side": side, "entry": float(entry_px), "amount": float(amount)}
    r.set(f"pos:{strategy}", json.dumps(rec), ex=7*24*3600)

def pop_open_entry(r: redis.Redis, strategy: str):
    k = f"pos:{strategy}"
    v = r.get(k)
    if not v: return None
    try: rec = json.loads(v)
    except: rec = None
    r.delete(k)
    return rec
