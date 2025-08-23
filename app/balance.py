from .config import Config
import json

# 선택: 공용 logger가 있으면 import 해서 log() 사용, 없으면 print로 대체
try:
    from .logger import log
except Exception:
    def log(event, **kw): 
        print(json.dumps({"event": event, **kw}, ensure_ascii=False))

def _pick_from_code(bucket: dict, code: str):
    if not isinstance(bucket, dict): 
        return {}
    # ccxt 표준 필드 우선 탐색
    cand = (
        bucket.get(code) 
        or bucket.get(f"{code}:USDT") 
        or bucket.get(f"{code}:USD")
        or {}
    )
    if cand:
        return cand
    # 일부 어댑터는 'balances' 하위에 둘 때가 있음
    bal2 = bucket.get("balances")
    if isinstance(bal2, dict):
        return (
            bal2.get(code) 
            or bal2.get(f"{code}:USDT") 
            or bal2.get(f"{code}:USD") 
            or {}
        )
    return {}

def _pick_amount(rec: dict, prefer: str):
    if not isinstance(rec, dict): 
        return 0.0
    order = [prefer, "free", "available", "total", "cash", "used"]
    for k in order:
        v = rec.get(k)
        if v is not None:
            try:
                return float(v)
            except Exception:
                pass
    return 0.0

def _parse_info_ev(info: dict) -> float:
    """Phemex 원시 info에서 잔고 필드를 직접 파싱 (Ev=1e8 스케일)"""
    if not isinstance(info, dict):
        return 0.0
    keys = [
        "availableBalanceEv", "totalBalanceEv", "accountBalanceEv",
        "cashBal", "totalWalletBalance",
    ]
    for k in keys:
        v = info.get(k)
        if v is None:
            continue
        try:
            vv = float(v)
            if vv > 1e6:   # Ev 스케일 추정
                vv = vv / 1e8
            if vv > 0:
                return vv
        except Exception:
            pass

    # 일부 응답: info.data.accounts[] 형태
    data = info.get("data") or info.get("accounts") or info.get("account")
    if isinstance(data, dict):
        # data.accounts 같은 배열 안에 currency/availableBalanceEv 가 있을 수 있음
        arr = data.get("accounts") or data.get("list") or data.get("items")
        if isinstance(arr, list):
            for acc in arr:
                try:
                    vv = float(acc.get("availableBalanceEv") or acc.get("cashBal") or 0)
                    if vv > 1e6:
                        vv = vv / 1e8
                    if vv > 0:
                        return vv
                except Exception:
                    pass
    return 0.0

def fetch_equity_generic(ex, cfg: Config):
    def _inner():
        variants = [
            {}, 
            {"type": "swap"},
            {"type": "future"},
            {"type": "contract"},
            {"code": cfg.equity_code},
        ]
        last_raw = None
        for params in variants:
            try:
                bal = ex.fetch_balance(params)
                last_raw = bal
                rec = _pick_from_code(bal, cfg.equity_code)
                amt = _pick_amount(rec, cfg.equity_source)
                if amt > 0:
                    log("balance_ok", params=params, code=cfg.equity_code, source=cfg.equity_source, picked=amt)
                    return amt
            except Exception as e:
                log("balance_fetch_error", params=params, error=str(e))

        # info에서 직접 파싱(여러 케이스 보강)
        try:
            info = (last_raw or {}).get("info")
            ev_amt = _parse_info_ev(info)
            if ev_amt > 0:
                log("balance_info_parsed", value=ev_amt)
                return ev_amt
        except Exception as e:
            log("balance_info_parse_error", error=str(e))

        # 0이면 스냅샷 로그로 힌트 제공
        snap = {}
        if isinstance(last_raw, dict):
            for k in ("free", "total", "used", "info"):
                if k in last_raw:
                    snap[k] = last_raw[k] if k != "info" else "INFO_PRESENT"
        log("balance_zero", hint="equity=0 (check testnet funding / EQUITY_CODE / EQUITY_SOURCE / ex instance)", snapshot=snap)
        return 0.0
    return _inner
