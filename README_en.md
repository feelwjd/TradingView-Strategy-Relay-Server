# TradingView‑Strategy‑Relay‑Server

> A lightweight webhook relay that receives TradingView alerts, validates and normalizes the payload, then places **contract orders on Phemex**. Designed for low‑latency execution and robust, idempotent handling of alerts.

---

## ✨ What this does

1. **TradingView Strategy → Webhook**  
   Your Pine strategy (e.g., **BULL — ETH Donchian ATR (5m, Long‑only, RT‑safe)**) emits alerts with structured JSON.

2. **Relay Server → Validation & Normalization**  
   The server verifies a shared secret, parses flexible fields (e.g., `action`, `reduceOnly|reduce_only`, `qtyPct|qty_pct`, `orderType|type`, `comment` as object or string), de‑dupes by `id`, and turns them into clean internal order intents.

3. **Execution → Phemex API**  
   Order intents are translated to Phemex REST/WebSocket calls (market/limit, reduce‑only partial exits, etc.).

---

## 🗺️ Architecture & Flow

```
TradingView (Pine v6 Strategy)
        │
        │ 1) Webhook (JSON)
        ▼
[ Relay Server (Python API) ]
  - Auth: shared secret
  - Schema: tolerant parser
  - Idempotency by `id`
  - Risk / symbol guards
        │
        │ 2) Normalized Order Intent
        ▼
[ Exchange Adapter (Phemex) ]
  - Market / Limit
  - Reduce‑only exits
  - Testnet/Mainnet
        │
        │ 3) Result & Logging
        ▼
   Storage / Logs / Metrics
```

---

## 🗂 Repository structure (typical)

```
.
├─ app/                 # Python app (API server, order translator/executor)
├─ nginx/               # Reverse proxy (TLS/headers/rate limits if enabled)
├─ Dockerfile           # App image
├─ docker-compose.yml   # Nginx + App composition
├─ requirements.txt     # Python deps
└─ .env.example         # Required environment variables
```

> Your exact layout may differ slightly. See `.env.example` for the authoritative list of environment variables.

---

## ⚙️ Quick start

### 1) Clone & configure

```bash
git clone https://github.com/feelwjd/TradingView-Strategy-Relay-Server.git
cd TradingView-Strategy-Relay-Server
cp .env.example .env
# Edit .env with your keys/secrets and preferences
```

**Common environment variables (example):**

- `RELAY_SHARED_SECRET` — shared secret checked on every webhook
- `PHEMEX_API_KEY`, `PHEMEX_API_SECRET` — your Phemex credentials
- `PHEMEX_BASE_URL` — mainnet or testnet base URL
- `PORT` — app listen port (if not proxied)
- `SYMBOL_ALLOWLIST` — optional CSV of tradable symbols (safety)
- `DEFAULT_ORDER_TYPE` — `market` or `limit`
- `DEFAULT_TP1_QTY_PCT` — default partial‑exit percentage if not provided
- `LOG_LEVEL` — `INFO`/`DEBUG`

> Use the values and names that match your actual implementation; the above is a common pattern.

### 2) Run with Docker Compose

```bash
docker compose up -d --build
```

- `nginx/` fronts the API and forwards `/webhook` (or your chosen path) to the Python app.
- The app binds internally (e.g., `:8000`); Nginx exposes the public port (e.g., `:80`/`:443`).

### 3) Point TradingView to your relay

In your TradingView alert, enable **Webhook URL** and set it to your relay endpoint (e.g., `https://YOUR_DOMAIN/webhook`).

---

## 🔌 API (relay) — request format

The server accepts **JSON** via `POST` (default path: `/webhook`, configurable behind Nginx).

### Common fields

| Field                | Type            | Required | Notes |
|---------------------|-----------------|----------|-------|
| `id`                | string          | ✅       | Unique per alert; used for idempotency (duplicates ignored). |
| `symbol`            | string          | ✅       | e.g., `PHEMEX:ETHUSDT.P` or exchange‑native symbol mapping. |
| `action`            | string          | ✅       | `"buy"`, `"sell"` (long entry / reduce/close depending on flags & side). |
| `price`             | number          | ✅*      | Used for limit orders or for logging with market orders. |
| `qtyPct`/`qty_pct`  | number (0‑100)  | ❌       | Percentage of current position to close on partial exits. |
| `reduceOnly`/`reduce_only` | bool     | ❌       | For partial exits/TP; **true** prevents net position increases. |
| `orderType`/`type`  | string          | ❌       | `"market"` or `"limit"`; default is market. |
| `comment`           | object or string| ❌       | Parsed safely (object preferred). Can carry `entry`, `sl`, `tp`, ATR, etc. |
| `relaySecret`       | string          | ✅       | Must match `RELAY_SHARED_SECRET`. |
| `strategy`          | string          | ❌       | Free tag (e.g., `"BULL"`). |

> The relay **accepts both camelCase and snake_case** variants on some fields for compatibility. Your Pine v6 example already follows this pattern for TP1 (`qtyPct` + `reduceOnly`).

### Example — Long entry (from your Pine)

```json
{
  "id": "BULL-LONG-<timenow>",
  "symbol": "{{ticker}}",
  "action": "buy",
  "price": 2564.7,
  "entry": 2564.7,
  "sl": 2550.1,
  "tp": 2610.3,
  "comment": { "entry": 2564.7, "sl": 2550.1, "tp": 2610.3, "atr": 7.2 },
  "relaySecret": "tonymin",
  "strategy": "BULL"
}
```

### Example — TP1 partial exit (reduce‑only)

```json
{
  "id": "BULL-TP1-<timenow>",
  "symbol": "{{ticker}}",
  "action": "sell",
  "reduceOnly": true,
  "qtyPct": 50,
  "price": 2590.0,
  "comment": { "kind": "tp1", "entry": 2564.7, "tp1Price": 2590.0 },
  "relaySecret": "tonymin",
  "strategy": "BULL"
}
```

---

## 🔁 Order translation & idempotency

- **Idempotency:** Alerts are keyed by `id`. If the same id is received twice (e.g., TradingView retries), duplicates are ignored harmlessly.
- **Action mapping:**
  - `action=buy` with no `reduceOnly` → open/increase long (market by default; limit if specified).
  - `action=sell` with `reduceOnly=true` → **partial/total close** of long (TP/stop/exit).
- **Order type:** `orderType|type = market|limit` (default: market).
- **Quantity:** For exits, `qtyPct` specifies how much of the current position to close. If missing on reduce‑only, the server can default to a sensible fraction or “all” (depending on your implementation).
- **Safety:** The relay enforces `relaySecret` and can use a symbol allow‑list / min‑max size guards.

---

## 🧠 About the Pine strategy (BULL — ETH Donchian ATR)

Your strategy (Pine v6) sends alerts and manages in‑chart exits for backtests:

- **Trigger:** Breakout of **Donchian channel high** on the 5‑minute chart (`lenDon`), with **RT‑safe** handling (intra‑bar `high > upper[1]` vs confirmed close).
- **Regime filter (optional):** Only trade when **ETH 4h** and **BTC 4h** are above their **EMA‑200**.
- **Risk model:**
  - **Initial SL/TP** via **ATR** multiples (`atrSLx`, `atrTPx`).
  - **TP1 scale‑out** at `tp1RR` R‑multiple; on hit, SL is **promoted to BE (+ticks)**.
  - **ATR trailing** after `trailRR` is reached (`atrTrailx`).
  - **Hard TP** can remain as a safety cap.
  - **Max holding time** (bars) can forcibly close positions.
- **Alerts:**
  - **Entry JSON** (`BULL-LONG-<timenow>`) includes top‑level `entry/sl/tp` and a `comment` object duplicate for robustness.
  - **TP1 JSON** (`BULL-TP1-<timenow>`) uses `reduceOnly: true` + `qtyPct`, with a semantic `comment` (`{kind:"tp1", ...}`).

This division keeps TradingView responsible for **signal generation and intent encoding**, while the relay handles **secure execution** and **exchange‑specific details**.

---

## 🧪 Local testing

Use `curl` to dry‑run your relay:

```bash
# 1) Health (if you expose it)
curl -i http://localhost:80/health

# 2) Simulate an entry alert
curl -sS -X POST http://localhost:80/webhook \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "TEST-LONG-123",
    "symbol": "PHEMEX:ETHUSDT.P",
    "action": "buy",
    "price": 2500.0,
    "entry": 2500.0, "sl": 2470.0, "tp": 2550.0,
    "comment": {"entry": 2500.0, "sl": 2470.0, "tp": 2550.0, "atr": 6.2},
    "relaySecret": "REPLACE_ME",
    "strategy": "BULL"
  }'
```

> Tip: point `PHEMEX_BASE_URL` to the **testnet** if you want to test without risk.

---

## 🔐 Security checklist

- Use a **long, unique `RELAY_SHARED_SECRET`** and rotate periodically.
- (Optional) Restrict Nginx to **allowlist TradingView IPs** or put the relay behind a VPN.
- Consider a **per‑strategy secret** (if you run multiple strategies).
- Enforce a **symbol allow‑list** and **min/max size** guards at the relay layer.

---

## 📦 Deploy notes

- **Dockerfile** builds the Python app; **docker‑compose** wires Nginx ↔ App and mounts your `.env`.
- Choose a region close to TradingView/Phemex for lower latency.
- Monitor with logs + metrics (e.g., request latency, error rates, order ACK times).

---

## ❓FAQ

**Q. Why duplicate `entry/sl/tp` at the top level *and* inside `comment`?**  
A. Redundancy makes the relay resilient to edge cases where one field might be missing or stringified. The server can prefer the object (`comment`) but still has top‑level fallbacks.

**Q. How do partial exits work?**  
A. Send `action:"sell"`, `reduceOnly:true`, and `qtyPct:<1..100>`. The relay converts this to a reduce‑only order on Phemex so your net exposure only decreases.

**Q. Market vs Limit?**  
A. Default is market. Add `orderType:"limit"` (or `type:"limit"`) plus `price` to request a limit. If omitted, `price` is treated as meta/for logging with market orders.

---

## 📝 License

MIT
