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
## TradingView alert setup

1. Add the strategy to your chart and adjust parameters.  
2. **Create Alert** → Condition: `Any alert() function call` (the strategy sends JSON via `alert()`).  
3. **Webhook URL**: `https://<your-relay>/webhook`.  
4. The alert body is produced by the script (e.g., `longJson`, `tp1Json`); you may leave the message field empty.

---

## Webhook JSON examples

**Entry (Binance)**

```json
{
  "id": "BULL-LONG-1700000000",
  "symbol": "BINANCE:ETHUSDT",
  "action": "buy",
  "price": "2345.6",
  "entry": "2345.6",
  "sl": "2270.3",
  "tp": "2530.2",
  "comment": {"entry":"2345.6","sl":"2270.3","tp":"2530.2","atr":"10.2"},
  "relaySecret": "REPLACE_ME",
  "strategy":"BULL"
}
```

**TP1 partial**

```json
{
  "id": "BULL-TP1-1700000001",
  "symbol": "BINANCE:ETHUSDT",
  "action": "sell",
  "reduceOnly": true,
  "qtyPct": 50,
  "price": "2355.0",
  "comment": {"kind":"tp1","entry":"2340.0","tp1Price":"2355.0"},
  "relaySecret":"REPLACE_ME",
  "strategy": "BULL"
}
```

> If using Phemex, send `symbol` like `PHEMEX:ETHUSDT.P` and set `EXCHANGE=phemex`.

---

## Pine strategy (logic summary)

- **Entry:** 5m Donchian high breakout (RT-safe)  
- **Risk:** ATR-based SL/TP multipliers  
- **Adaptive exits:** TP1 partial → promote SL to BE → ATR trailing  
- **Options:** keep hard TP, time-based close for over-held positions  
- **Regime filter:** optional 4h EMA200 confirmation on ETH & BTC  
- **Alerts:** sends entry/TP1 JSON via `alert()`

---
![strategy](https://github.com/user-attachments/assets/32ff6646-5fd2-47ec-8b18-1c89aa9d63f6)
## Full Pine script

> Also shipped as a file: [`pine/BULL_ETH_Donchian_ATR_v4.pine`](./pine/BULL_ETH_Donchian_ATR_v4.pine)

```pinescript
//@version=6
strategy("BULL — ETH Donchian ATR (5m, Long-only, RT-safe)_v4",
     overlay=true, calc_on_every_tick=true, process_orders_on_close=false, pyramiding=0,
     initial_capital=1000, default_qty_type=strategy.percent_of_equity, default_qty_value=10)

// ===== Inputs =====
groupI  = "Inputs"
lenDon  = input.int(20, "Donchian Length (5m)", 10, 50, group=groupI)
atrLen  = input.int(14, "ATR Length", 5, 50, group=groupI)
atrSLx  = input.float(2.5, "SL = ATR x", step=0.1, group=groupI)
atrTPx  = input.float(4.5, "TP = ATR x", step=0.1, group=groupI)

// ===== Adaptive Exit Inputs =====
groupE       = "Exits — Adaptive (win-rate focus)"
useTP1       = input.bool(true,  "TP1 스케일아웃 & BE 승격", group=groupE)
tp1RR        = input.float(1.0,  "TP1 트리거 RR=", step=0.1, group=groupE)   // 초기위험 대비 1R에서 1차 청산
tp1Pct       = input.int(50,     "TP1 청산 비중(%)", minval=1, maxval=90, group=groupE)
beTicks      = input.int(2,      "BE 오프셋(틱)", minval=0, group=groupE)     // BE를 약간 위로
useTrail     = input.bool(true,  "ATR 트레일링 사용", group=groupE)
trailRR      = input.float(1.5,  "트레일링 시작 RR>=", step=0.1, group=groupE)
atrTrailx    = input.float(2.0,  "트레일링 ATR 배수", step=0.1, group=groupE)
useHardTP    = input.bool(true,  "최종 하드 TP 유지(세이프티)", group=groupE)
useTimeExit  = input.bool(true,  "보유시간 기준 청산", group=groupE)
maxBarsHold  = input.int(72,     "최대 보유 바 수(5m)", minval=1, group=groupE) // 72=약 6시간


// 세션/요일 기본 OFF (진입 확인용으로 막힘 제거)
groupS = "Session / Weekday Filter"
useSess = input.bool(false, "Limit by active session?", group=groupS)
sessA   = input.session("1100-1659", "Session A (BULL 추천)", group=groupS)
sessB   = input.session("",          "Session B (optional)", group=groupS)
useDays = input.bool(false, "Limit by weekday?", group=groupS)
dMon = input.bool(true,  "Mon", group=groupS)
dTue = input.bool(true,  "Tue", group=groupS)
dWed = input.bool(true,  "Wed", group=groupS)
dThu = input.bool(true,  "Thu", group=groupS)
dFri = input.bool(false, "Fri", group=groupS)
dSat = input.bool(true,  "Sat", group=groupS)
dSun = input.bool(true,  "Sun", group=groupS)

// 레짐(옵션)
groupF = "Regime Filter"
useLocalReg = input.bool(false, "Use Local 4h EMA200 Regime (ETH & BTC)", group=groupF)
useChartSym = input.bool(true, "Use Chart Symbol (recommended)", group=groupF)
sym      = useChartSym ? syminfo.tickerid : input.symbol("PHEMEX:ETHUSDT.P", "Symbol (if not using chart)", group=groupF)
btcSym   = input.symbol("PHEMEX:BTCUSDT", "BTC Regime Symbol (Phemex)", group=groupF)

// Debug
groupD = "Debug"
dbgAlert = input.bool(true, "Send debug alert on trigger", group=groupD)
dbgPlot  = input.bool(true, "Plot trigger markers", group=groupD)

// ===== Helpers =====
fnum(x) => str.tostring(x, format.mintick)

// ===== Exit State (persistent) =====
var float entryPx   = na
var float initSL    = na
var float initRisk  = na
var float peakHigh  = na
var int   barsInPos = 0


// ===== Session/Weekday gating =====
_inSessA = useSess ? not na(time(timeframe.period, sessA)) : true
_inSessB = useSess and (str.length(sessB) > 0) ? not na(time(timeframe.period, sessB)) : false
_inSess  = useSess ? (_inSessA or _inSessB) : true

_dow = dayofweek
var bool _inDays = true
if useDays
    isMon = _dow == dayofweek.monday    and dMon
    isTue = _dow == dayofweek.tuesday   and dTue
    isWed = _dow == dayofweek.wednesday and dWed
    isThu = _dow == dayofweek.thursday  and dThu
    isFri = _dow == dayofweek.friday    and dFri
    isSat = _dow == dayofweek.saturday  and dSat
    isSun = _dow == dayofweek.sunday    and dSun
    _inDays := isMon or isTue or isWed or isThu or isFri or isSat or isSun
else
    _inDays := true

tradeWindow = _inSess and _inDays

// ===== 5m Core Series =====
var bool is5 = timeframe.period == "1"
float upper = na
float atrV  = na
if is5
    upper := ta.highest(high, lenDon)
    atrV  := ta.atr(atrLen)
else
    upper := request.security(sym, "1", ta.highest(high, lenDon), lookahead=barmerge.lookahead_off)
    atrV  := request.security(sym, "1", ta.atr(atrLen),              lookahead=barmerge.lookahead_off)

// ===== Optional local regime (ETH/BTC 4h EMA200 동반 상방) =====
float ema4h_eth = ta.ema(request.security(sym,    "240", close, lookahead=barmerge.lookahead_off), 200)
float ema4h_btc = ta.ema(request.security(btcSym, "240", close, lookahead=barmerge.lookahead_off), 200)
float btc_px_4h = request.security(btcSym, "240", close, lookahead=barmerge.lookahead_off)

bool locBull = not na(ema4h_eth) and not na(ema4h_btc) and not na(btc_px_4h) and close > ema4h_eth and btc_px_4h > ema4h_btc
bool regPass = not useLocalReg or locBull

// ===== Trigger (RT-safe) =====
validBand  = not na(upper[1])
bool rtBreak    = validBand and high  > upper[1]
bool closeBreak = validBand and close > upper[1]
longTrig = regPass and tradeWindow and (barstate.isconfirmed ? closeBreak : rtBreak)

// ===== SL/TP =====
longSL = close - atrSLx * atrV
longTP = close + atrTPx * atrV

// 서버용 comment(JSON fragment)
longComm = "{" + "\"entry\":" + fnum(close) + "," + "\"sl\":" + fnum(longSL) + "," + "\"tp\":" + fnum(longTP) + "," + "\"atr\":" + fnum(atrV) + "}"

// ===== Alerts(Webhook) =====
useSignalAlerts = input.bool(true, "Enable Signal Alerts (alert())", inline="al")
relaySecret     = input.string("tonymin", "Relay Secret", inline="al")
strategyTag     = input.string("BULL", "Strategy Tag", inline="al")

string uid   = str.tostring(timenow)
string idStr = "BULL-LONG-" + uid        // 진입용
string idExit= "BULL-EXIT-" + uid        // (필요시) 청산용

// longComm 은 {"entry":...} 형태의 문자열
string commentEsc = str.replace(longComm, "\"", "\\\"")
// comment를 객체(longComm) 그대로 넣는다 (따옴표로 감싸지 않음)
string longJson =
  "{\"id\":\"" + idStr + "\",\"symbol\":\"" + syminfo.ticker +
  "\",\"action\":\"buy\",\"price\":" + fnum(close) +
  // ⬇⬇⬇ 톱레벨 중복 전달
  ",\"entry\":" + fnum(close) + ",\"sl\":" + fnum(longSL) + ",\"tp\":" + fnum(longTP) +
  // ⬇ 기존 comment(객체)도 그대로
  ",\"comment\":" + longComm +
  ",\"relaySecret\":\"" + relaySecret + "\",\"strategy\":\"" + strategyTag + "\"}"
// ===== Orders (인트라바 진입 허용) =====
longOK = longTrig  // ⬅ 확정바 강제 제거

if longOK and strategy.position_size == 0
    strategy.entry("BULL-LONG", strategy.long, comment=longComm)
    if dbgAlert
        alert("DEBUG BULL longTrig: " + syminfo.ticker + " @ " + fnum(close), alert.freq_once_per_bar)

// ===== 포지션 상태 추적 =====
if strategy.position_size > 0
    // 포지션 진입 직후 1회 초기화
    if na(entryPx)
        entryPx   := strategy.position_avg_price
        initSL    := entryPx - atrSLx * atrV
        initRisk  := math.max(entryPx - initSL, syminfo.mintick)
        peakHigh  := high
        barsInPos := 0
    else
        peakHigh  := math.max(peakHigh, high)
        barsInPos += 1
else
    entryPx   := na
    initSL    := na
    initRisk  := na
    peakHigh  := na
    barsInPos := 0

// ===== 동적 EXIT 계산 =====
float tp1Price = na(entryPx) ? na : entryPx + tp1RR * initRisk
float bePrice  = na(entryPx) ? na : entryPx + beTicks * syminfo.mintick
bool  hitTP1   = not na(tp1Price) and high >= tp1Price

bool  enableTrail = useTrail and not na(entryPx) and ((trailRR <= 0) or (high >= entryPx + trailRR * initRisk))
float trailSL  = not na(peakHigh) ? (peakHigh - atrTrailx * atrV) : na

float slNow = na
slNow := na(initSL) ? na : initSL
if useTP1 and hitTP1
    slNow := math.max(slNow, bePrice)      // TP1 체결로 가정 → BE 승격
if enableTrail and not na(trailSL)
    slNow := math.max(slNow, trailSL)      // 트레일링이 더 위라면 채택

// (옵션) 최종 하드 TP를 유지해 꼬리 구간 과도한 반납 방지
float tpNow = na
if useHardTP and not na(entryPx)
    tpNow := entryPx + atrTPx * initRisk

// TP1 스케일아웃: 포지션 일부를 RR=tp1RR 에서 청산
if useTP1 and not na(tp1Price) and strategy.position_size > 0
    strategy.exit("BULL-TP1", from_entry="BULL-LONG", limit=tp1Price, qty_percent=tp1Pct)

// 나머지 물량: 동적 SL(= 초기SL/BE/트레일링 중 최댓값) + (옵션) 하드 TP
if strategy.position_size > 0
    strategy.exit("BULL-EXIT", from_entry="BULL-LONG", stop=slNow, limit=tpNow)

// 보유시간 초과 시 시장가 청산 (정상)
if useTimeExit and strategy.position_size > 0 and barsInPos >= maxBarsHold
    strategy.close("BULL-LONG")

// === TP1 체결 시 부분청산 웹훅 보내기 ===
var bool tp1Sent = false
if strategy.position_size > 0 and useTP1 and hitTP1 and not tp1Sent
    tp1Sent := true
    string uid1   = str.tostring(timenow)
    string idTp1  = "BULL-TP1-" + uid1
    // 서버가 parse_comment_field()로 안전 파싱하므로 그대로 객체 형태 전달 OK
    string tp1Json =
      "{\"id\":\"" + idTp1 + "\",\"symbol\":\"" + syminfo.ticker + "\",\"action\":\"sell\"" +
      ",\"reduceOnly\":true,\"qtyPct\":" + str.tostring(tp1Pct) + // ✅ % 단위(예: 50)
      ",\"price\":" + fnum(close) +
      ",\"comment\":{\"kind\":\"tp1\",\"entry\":" + fnum(entryPx) + ",\"tp1Price\":" + fnum(tp1Price) + "}" +
      ",\"relaySecret\":\"" + relaySecret + "\",\"strategy\":\"BULL\"}"

    if useSignalAlerts
        alert(tp1Json)

// ===== Visuals =====
plotshape(dbgPlot and longOK, title="BULL trig", style=shape.triangleup, color=color.new(color.green, 0), size=size.tiny, location=location.belowbar, text="BULL")
plotchar(dbgPlot and tradeWindow, title="TW", char="T", location=location.bottom, size=size.tiny, color=color.new(color.green, 0))
plotchar(dbgPlot and regPass,     title="RG", char="R", location=location.bottom, size=size.tiny, color=color.new(color.green, 0))
plot(ema4h_eth, "EMA200 4h (ETH)", color=color.teal, linewidth=2)
plot(upper,      "Donchian High (5m)", color=color.new(color.green, 0))

// ===== Alertconditions (고정 메시지) =====
alertcondition(longOK, "BULL — entry trigger", "BULL entry trigger")

if useSignalAlerts and longOK
    alert(longJson)


// ===== 5m Core Series =====
float donHigh = na
float donLow  = na

donHigh := ta.highest(high, lenDon)
donLow  := ta.lowest(low,  lenDon)
atrV    := ta.atr(atrLen)

```

---

## Security & ops

- Enforce HTTPS, use a strong `RELAY_SHARED_SECRET`  
- Keep API keys out of the repo (env only)  
- Symbol allowlist, min-size checks, idempotency on `id`  
- Thoroughly test on paper-trade/testnet before live

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
