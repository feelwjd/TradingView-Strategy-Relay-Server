import re

def tv_to_ccxt_symbol(tv_symbol: str):
    if not tv_symbol: return None
    s = tv_symbol.strip().upper()
    if ":" in s:
        s = s.split(":")[-1]
    if s.endswith(".P"):
        s = s[:-2]
    m = re.match(r"^([A-Z]+)(USDT|USD)$", s)
    if not m:
        if "/" in s and ":" in s:
            return s
        return None
    base, quote = m.group(1), m.group(2)
    return f"{base}/USDT:USDT" if quote=="USDT" else f"{base}/USD:USD"

def normalize_symbol_for_exchange(sym: str, exchange_id: str):
    if not sym: return None
    s = sym.strip()
    if exchange_id == "phemex":
        return tv_to_ccxt_symbol(s) or "ETH/USDT:USDT"
    elif exchange_id == "binance":
        if ":" in s: s = s.split(":")[0]
        m = re.match(r"^([A-Za-z]+)(USDT)$", s, re.I)
        if m and "/" not in s:
            s = f"{m.group(1).upper()}/USDT"
        return s.upper()
    return s
