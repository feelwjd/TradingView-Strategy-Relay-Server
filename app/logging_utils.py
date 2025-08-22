import json, logging

SENSITIVE_KEYS = {
    "relaySecret","signalToken",
    "PHEMEX_SECRET","PHEMEX_API_KEY",
    "PHEMEX_API_KEY_DEV","PHEMEX_SECRET_DEV","PHEMEX_API_KEY_PROD","PHEMEX_SECRET_PROD",
    "REGIME_PHEMEX_API_KEY_DEV","REGIME_PHEMEX_SECRET_DEV","REGIME_PHEMEX_API_KEY_PROD","REGIME_PHEMEX_SECRET_PROD",
    "REGIME_BINANCE_API_KEY_DEV","REGIME_BINANCE_SECRET_DEV","REGIME_BINANCE_API_KEY_PROD","REGIME_BINANCE_SECRET_PROD"
}

def setup_logger(json_mode: bool, level: str, to_file: bool, file_path: str) -> logging.Logger:
    logger = logging.getLogger("relay")
    logger.setLevel(getattr(logging, level, logging.INFO))
    handler = logging.FileHandler(file_path) if to_file else logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    if not logger.handlers:
        logger.addHandler(handler)
    return logger

def redact(d: dict) -> dict:
    try:
        x = dict(d)
        for k in list(x.keys()):
            if k in SENSITIVE_KEYS and x.get(k) is not None:
                x[k] = "***REDACTED***"
        return x
    except Exception:
        return {}

def log(logger: logging.Logger, json_mode: bool, event: str, **kwargs):
    rec = {"ts": __import__("time").time()*1000, "event": event}
    rec.update(kwargs)
    if json_mode: logger.info(json.dumps(rec, ensure_ascii=False))
    else:         logger.info(f"{rec}")
