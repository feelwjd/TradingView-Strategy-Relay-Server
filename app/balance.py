from .config import Config

def _pick_from_code(bucket: dict, code: str):
    if not isinstance(bucket, dict): return {}
    return (bucket.get(code) or bucket.get(f"{code}:USDT") or bucket.get(f"{code}:USD") or {})

def _pick_amount(rec: dict, prefer: str):
    if not isinstance(rec, dict): return 0.0
    order = [prefer, "free", "available", "total", "cash"]
    for k in order:
        v = rec.get(k)
        if v is not None:
            try: return float(v)
            except: pass
    return 0.0

def fetch_equity_generic(ex, cfg: Config):
    def _inner():
        variants = [{},{ "type":"swap"},{"type":"future"},{"type":"contract"},{"code":cfg.equity_code}]
        last_raw = None
        for params in variants:
            try:
                bal = ex.fetch_balance(params)
                last_raw = bal
                rec = _pick_from_code(bal, cfg.equity_code)
                amt = _pick_amount(rec, cfg.equity_source)
                if amt > 0:
                    return amt
            except Exception:
                pass
        try:
            info = (last_raw or {}).get("info")
            if isinstance(info, dict):
                keys = ["totalBalanceEv","accountBalanceEv","availableBalanceEv","cashBal","totalWalletBalance"]
                for k in keys:
                    v = info.get(k)
                    if v is not None:
                        try:
                            vv = float(v)
                            if vv > 1e6: vv = vv / 1e8
                            if vv > 0: return vv
                        except: pass
        except Exception:
            pass
        return 0.0
    return _inner
