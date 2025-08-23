# app/config.py
import os
from dataclasses import dataclass

# .env 자동 로드 (main.py에서 불러도 중복 호출 안전)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

def _env_bool(key: str, default: bool = False) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")

def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except Exception:
        return default

def _env_int(key: str, default: int) -> int:
    try:
        return int(float(os.getenv(key, str(default))))
    except Exception:
        return default

@dataclass
class Config:
    # Trade(Phemex)
    trade_testnet: bool
    phemex_api_key_dev: str
    phemex_secret_dev: str
    phemex_api_key_prod: str
    phemex_secret_prod: str
    api_key_fallback: str
    api_sec_fallback: str

    # Regime source
    regime_exchange: str         # "binance" | "phemex"
    regime_testnet: bool
    regime_binance_market: str   # "spot" | "usdm"
    regime_binance_key_dev: str
    regime_binance_sec_dev: str
    regime_binance_key_prod: str
    regime_binance_sec_prod: str
    regime_phemex_key_dev: str
    regime_phemex_sec_dev: str
    regime_phemex_key_prod: str
    regime_phemex_sec_prod: str
    regime_symbol_eth: str
    regime_symbol_btc: str

    # Fallback symbol
    symbol_fallback: str

    # Redis / Idempotency
    redis_url: str
    idempotency_ttl: int

    # Risk & Order
    max_slippage: float
    fee_buffer: float
    recon_retries: int
    recon_wait: float
    use_mark_price: bool
    taker_fee: float
    min_notional_usdt: float

    # Sizing defaults
    server_sizing: bool
    sizing_mode: str
    risk_pct: float
    alloc_pct: float
    lev_default: int
    margin_buffer: float

    # Regime gate (alloc/leverage map)
    alloc_bull_bull: float
    alloc_bull_neutral: float
    alloc_bull_bear: float
    lev_bull_bull: int
    lev_bull_neutral: int
    lev_bull_bear: int

    alloc_bear_bull: float
    alloc_bear_neutral: float
    alloc_bear_bear: float
    lev_bear_bull: int
    lev_bear_neutral: int
    lev_bear_bear: int

    # Cooldown / DD
    loss_streak_limit_bull: int
    loss_streak_limit_bear: int
    cooldown_min_bull: int
    cooldown_min_bear: int
    daily_max_dd_usdt: float

    # Funding/VIX/Edge
    funding_abs_max: float
    assume_hold_hours: float
    vix_url: str
    vix_max: float

    # Logging
    log_level: str
    log_json: bool
    log_to_file: bool
    log_file: str

    # Equity
    equity_code: str
    equity_source: str
    balance_debug: bool

    relay_shared_secret: str

    # === Edge / Funding / TP policy ===
    edge_filter_enabled: bool
    min_edge_usdt: float
    holding_hours_est: float        # used in expected_edge_usdt()
    edge_require_tp: bool
    edge_allow_derive_tp: bool
    edge_atr_tp_x: float

    # === Risk sizing safety ===
    risk_atr_fallback_x: float
    risk_min_dist_ticks: int
    risk_hard_reject: bool
    allow_bump_to_min_order: bool

    phemex_position_mode: str   # "oneway" | "hedge"
    phemex_hedged: bool         # True if hedge

    @staticmethod
    def from_env() -> "Config":
        pos_mode_raw = os.getenv("PHEMEX_POSITION_MODE", "oneway").strip().lower()
        pos_mode = "hedge" if pos_mode_raw in ("hedge", "hedged", "dual", "dual_side", "dual-side", "dualside") else "oneway"
        hedged = (pos_mode == "hedge")
        
        return Config(
            # Trade
            trade_testnet=_env_bool("PHEMEX_TESTNET", True),
            phemex_api_key_dev=os.getenv("PHEMEX_API_KEY_DEV", ""),
            phemex_secret_dev=os.getenv("PHEMEX_SECRET_DEV", ""),
            phemex_api_key_prod=os.getenv("PHEMEX_API_KEY_PROD", ""),
            phemex_secret_prod=os.getenv("PHEMEX_SECRET_PROD", ""),
            api_key_fallback=os.getenv("PHEMEX_API_KEY", ""),
            api_sec_fallback=os.getenv("PHEMEX_SECRET", ""),

            phemex_position_mode=pos_mode,
            phemex_hedged=hedged,
            
            # Regime
            regime_exchange=os.getenv("REGIME_EXCHANGE", "binance").lower(),
            regime_testnet=_env_bool("REGIME_TESTNET", False),
            regime_binance_market=os.getenv("REGIME_BINANCE_MARKET", "spot").lower(),
            regime_binance_key_dev=os.getenv("REGIME_BINANCE_API_KEY_DEV", ""),
            regime_binance_sec_dev=os.getenv("REGIME_BINANCE_SECRET_DEV", ""),
            regime_binance_key_prod=os.getenv("REGIME_BINANCE_API_KEY_PROD", ""),
            regime_binance_sec_prod=os.getenv("REGIME_BINANCE_SECRET_PROD", ""),
            regime_phemex_key_dev=os.getenv("REGIME_PHEMEX_API_KEY_DEV", ""),
            regime_phemex_sec_dev=os.getenv("REGIME_PHEMEX_SECRET_DEV", ""),
            regime_phemex_key_prod=os.getenv("REGIME_PHEMEX_API_KEY_PROD", ""),
            regime_phemex_sec_prod=os.getenv("REGIME_PHEMEX_SECRET_PROD", ""),
            regime_symbol_eth=os.getenv("REGIME_SYMBOL_ETH", ""),
            regime_symbol_btc=os.getenv("REGIME_SYMBOL_BTC", ""),

            # Symbols
            symbol_fallback=os.getenv("SYMBOL", "ETH/USDT:USDT"),

            # Redis
            redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0"),
            idempotency_ttl=_env_int("IDEMPOTENCY_TTL", 900),

            # Risk & Order
            max_slippage=_env_float("MAX_SLIPPAGE", 0.004),
            fee_buffer=_env_float("FEE_BUFFER", 0.003),
            recon_retries=_env_int("RECONCILE_RETRIES", 8),
            recon_wait=_env_float("RECONCILE_INTERVAL", 1.5),
            use_mark_price=_env_bool("USE_MARK_PRICE", True),
            taker_fee=_env_float("TAKER_FEE", 0.0006),
            min_notional_usdt=_env_float("MIN_NOTIONAL_USDT", 5.0),

            # Sizing
            server_sizing=_env_bool("SERVER_SIZING", True),
            sizing_mode=os.getenv("SIZING_MODE", "notional").lower(),
            risk_pct=_env_float("RISK_PCT", 0.004),
            alloc_pct=_env_float("ALLOC_PCT", 0.50),
            lev_default=_env_int("LEVERAGE_DEFAULT", 20),
            margin_buffer=_env_float("MARGIN_BUFFER", 0.98),

            # Regime Gate
            alloc_bull_bull=_env_float("ALLOC_BULL_BULL", 0.50),
            alloc_bull_neutral=_env_float("ALLOC_BULL_NEUTRAL", 0.25),
            alloc_bull_bear=_env_float("ALLOC_BULL_BEAR", 0.10),
            lev_bull_bull=_env_int("LEV_BULL_BULL", 8),
            lev_bull_neutral=_env_int("LEV_BULL_NEUTRAL", 6),
            lev_bull_bear=_env_int("LEV_BULL_BEAR", 3),

            alloc_bear_bull=_env_float("ALLOC_BEAR_BULL", 0.00),
            alloc_bear_neutral=_env_float("ALLOC_BEAR_NEUTRAL", 0.10),
            alloc_bear_bear=_env_float("ALLOC_BEAR_BEAR", 0.50),
            lev_bear_bull=_env_int("LEV_BEAR_BULL", 3),
            lev_bear_neutral=_env_int("LEV_BEAR_NEUTRAL", 4),
            lev_bear_bear=_env_int("LEV_BEAR_BEAR", 8),

            # Cooldown/DD
            loss_streak_limit_bull=_env_int("LOSS_STREAK_LIMIT_BULL", 5),
            loss_streak_limit_bear=_env_int("LOSS_STREAK_LIMIT_BEAR", 4),
            cooldown_min_bull=_env_int("COOLDOWN_MIN_BULL", 90),
            cooldown_min_bear=_env_int("COOLDOWN_MIN_BEAR", 120),
            daily_max_dd_usdt=_env_float("DAILY_MAX_DD_USDT", 0.0),

            # Funding/VIX/Edge inputs
            funding_abs_max=_env_float("FUNDING_ABS_MAX", 0.0003),
            assume_hold_hours=_env_float("ASSUME_HOLD_HOURS", 2.0),
            vix_url=os.getenv("VIX_URL", ""),
            vix_max=_env_float("VIX_MAX", 30.0),

            # Logging
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            log_json=_env_bool("LOG_JSON", True),
            log_to_file=_env_bool("LOG_TO_FILE", False),
            log_file=os.getenv("LOG_FILE", "/app/relay.log"),

            # Equity
            equity_code=os.getenv("EQUITY_CODE", "USDT").upper(),
            equity_source=os.getenv("EQUITY_SOURCE", "free").lower(),
            balance_debug=_env_bool("BALANCE_DEBUG", True),

            relay_shared_secret=os.getenv("RELAY_SHARED_SECRET", ""),

            # Edge / TP policy
            edge_filter_enabled=_env_bool("EDGE_FILTER_ENABLED", True),
            min_edge_usdt=_env_float("MIN_EDGE_USDT", 0.0),
            holding_hours_est=_env_float(
                "HOLDING_HOURS_EST",
                _env_float("ASSUME_HOLD_HOURS", 8.0)  # backward compat
            ),
            edge_require_tp=_env_bool("EDGE_REQUIRE_TP", False),
            edge_allow_derive_tp=_env_bool("EDGE_ALLOW_DERIVE_TP", True),
            edge_atr_tp_x=_env_float("EDGE_ATR_TP_X", 3.0),

            # Risk sizing safety
            risk_atr_fallback_x=_env_float("RISK_ATR_FALLBACK_X", 2.0),
            risk_min_dist_ticks=_env_int("RISK_MIN_DIST_TICKS", 1),
            risk_hard_reject=_env_bool("RISK_HARD_REJECT", False),
            allow_bump_to_min_order=_env_bool("ALLOW_BUMP_TO_MIN_ORDER", True),
        )
