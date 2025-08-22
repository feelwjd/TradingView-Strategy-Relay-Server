import time
from fastapi import FastAPI
from dotenv import load_dotenv
from .config import Config
from .logging_utils import setup_logger
from .redis_utils import connect as redis_connect
from .exchanges import build_exchanges
from .webhook import router as api_router

load_dotenv()

def create_app() -> FastAPI:
    cfg = Config.from_env()
    logger = setup_logger(cfg.log_json, cfg.log_level, cfg.log_to_file, cfg.log_file)
    r = redis_connect(cfg.redis_url)
    ex, ex_regime = build_exchanges(cfg)

    app = FastAPI(title="Phemex Relay (Modular)", version="1.3.0")
    app.state.cfg = cfg
    app.state.logger = logger
    app.state.r = r
    app.state.ex = ex
    app.state.ex_regime = ex_regime
    app.state.app_start = time.time()

    app.include_router(api_router)
    return app

app = create_app()
