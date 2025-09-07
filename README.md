# TradingView‑Strategy‑Relay‑Server

> TradingView 알림을 수신하여 페이로드를 **검증·정규화**하고, **Phemex**에 선물/계약 주문을 집행하는 경량 **웹훅 릴레이 서버**입니다. 저지연 실행과 **멱등성(idempotency)** 기반의 안정적인 재시도 처리에 초점을 두었습니다.

---

## ✨ 동작 개요

1. **TradingView 전략 → Webhook**  
   Pine 전략(예: **BULL — ETH Donchian ATR (5m, Long‑only, RT‑safe)**)이 구조화된 JSON 알림을 발생합니다.

2. **릴레이 서버 → 검증 & 정규화**  
   공유 시크릿을 확인하고, 유연한 스키마(예: `action`, `reduceOnly|reduce_only`, `qtyPct|qty_pct`, `orderType|type`, `comment` 객체/문자열)를 파싱하여 내부 **주문 의도**로 변환합니다. `id`로 중복을 제거합니다.

3. **실행 → Phemex API**  
   주문 의도를 Phemex REST/WebSocket 호출로 변환하여 **시장가/지정가**, **reduce‑only 부분청산** 등을 수행합니다.

---

## 🗺️ 아키텍처 & 흐름

```
TradingView (Pine v6 전략)
        │
        │ 1) Webhook (JSON)
        ▼
[ Relay Server (Python API) ]
  - 인증: shared secret
  - 스키마: 관대한 파서
  - 멱등성: `id` 기준
  - 리스크/심볼 가드
        │
        │ 2) 정규화된 주문 의도
        ▼
[ Exchange Adapter (Phemex) ]
  - 시장가 / 지정가
  - Reduce‑only 청산
  - Testnet / Mainnet
        │
        │ 3) 결과 & 로깅
        ▼
   저장 / 로그 / 메트릭
```

---

## 🗂 저장소 구조(예시)

```
.
├─ app/                 # Python 앱 (API 서버, 주문 변환/집행)
├─ nginx/               # 리버스 프록시 (TLS/헤더/레이트 리밋 등)
├─ Dockerfile           # 앱 이미지
├─ docker-compose.yml   # Nginx + App 컴포지션
├─ requirements.txt     # Python 의존성
└─ .env.example         # 필수 환경변수 샘플
```

> 실제 레이아웃은 약간 다를 수 있습니다. 환경변수 목록은 `.env.example`을 기준으로 확인하세요.

---

## ⚙️ 빠른 시작

### 1) 클론 & 설정

```bash
git clone https://github.com/feelwjd/TradingView-Strategy-Relay-Server.git
cd TradingView-Strategy-Relay-Server
cp .env.example .env
# .env 를 열어 키/시크릿과 선호 설정을 입력
```

**주요 환경변수(예):**

- `RELAY_SHARED_SECRET` — 모든 웹훅에서 확인하는 공유 시크릿
- `PHEMEX_API_KEY`, `PHEMEX_API_SECRET` — Phemex 인증키
- `PHEMEX_BASE_URL` — 메인넷/테스트넷 베이스 URL
- `PORT` — 앱 리슨 포트(Nginx 비사용 시)
- `SYMBOL_ALLOWLIST` — 허용 심볼 CSV(선택, 안전장치)
- `DEFAULT_ORDER_TYPE` — `market` 또는 `limit`
- `DEFAULT_TP1_QTY_PCT` — 부분청산 기본 비율(미전달 시)
- `LOG_LEVEL` — `INFO`/`DEBUG`

> 실제 구현의 키 이름/값에 맞춰 사용하세요. 위 목록은 일반적인 패턴입니다.

### 2) Docker Compose 실행

```bash
docker compose up -d --build
```

- `nginx/`가 API를 전면에서 받고 `/webhook`(혹은 지정 경로)을 Python 앱으로 프록시합니다.
- 앱은 내부 포트(예: `:8000`)에 바인딩, Nginx가 외부 포트(예: `:80`/`:443`)를 노출합니다.

### 3) TradingView 웹훅 연결

TradingView 알림에서 **Webhook URL**을 활성화하고, 릴레이 엔드포인트(예: `https://YOUR_DOMAIN/webhook`)를 입력하세요.

---

## 🔌 API (relay) — 요청 포맷

기본적으로 `POST /webhook` 경로(환경에 따라 변경 가능)로 **JSON**을 수신합니다.

### 공통 필드

| 필드                  | 타입             | 필수 | 설명 |
|----------------------|------------------|------|------|
| `id`                 | string           | ✅   | 알림 고유값. 멱등성 키(중복 무시). |
| `symbol`             | string           | ✅   | 예: `PHEMEX:ETHUSDT.P` 또는 거래소 심볼 맵핑. |
| `action`             | string           | ✅   | `"buy"`, `"sell"` (진입/청산). |
| `price`              | number           | ✅*  | 지정가 주문 가격 또는 시장가 참고용. |
| `qtyPct`/`qty_pct`   | number (0‑100)   | ❌   | 부분청산 비율(퍼센트). |
| `reduceOnly`/`reduce_only` | bool      | ❌   | 부분청산/TP에서 **포지션 증가 방지**. |
| `orderType`/`type`   | string           | ❌   | `"market"` 또는 `"limit"`; 기본값 `market`. |
| `comment`            | object or string | ❌   | 안전 파싱. `entry`, `sl`, `tp`, ATR 등 메타 포함 가능. |
| `relaySecret`        | string           | ✅   | `RELAY_SHARED_SECRET` 일치 필요. |
| `strategy`           | string           | ❌   | 자유 태그(예: `"BULL"`). |

> 호환성을 위해 일부 필드는 **camelCase / snake_case** 둘 다 수용합니다. TP1의 `qtyPct` + `reduceOnly`처럼 사용하세요.

### 예시 — 롱 진입(전략 발신)

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

### 예시 — TP1 부분청산(reduce‑only)

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

## 🔁 주문 변환 & 멱등성

- **멱등성:** `id`를 키로 중복 알림을 무해하게 무시합니다(TradingView 재시도 등).
- **액션 매핑:**
  - `action=buy` & `reduceOnly` 없음 → 롱 신규/증가(기본 시장가; 지정가 지정 시 `limit`).
  - `action=sell` & `reduceOnly=true` → **부분/전량 청산**(TP/스탑/종료).
- **주문 타입:** `orderType|type = market|limit` (기본 `market`).
- **수량:** 청산에서는 `qtyPct`로 닫을 비율을 지정. 생략 시 구현에 따라 기본값/전량 처리.
- **안전장치:** `relaySecret` 검증, 심볼 허용 목록, 최소/최대 수량 가드 등 구성 가능.

---

## 🧠 Pine 전략 설명 (BULL — ETH Donchian ATR)

작성하신 Pine v6 전략은 알림 발신과 백테스트용 차트 내 청산 로직을 포함합니다.

- **트리거:** 5분 봉 **Donchian 상단 돌파**(`lenDon`), **RT‑safe** 처리(확정 종가 vs. 인트라바 `high > upper[1]`).
- **레짐 필터(선택):** **ETH 4h**와 **BTC 4h**가 **EMA‑200 상단**에 있을 때만 매수.
- **리스크 모델:**
  - **초기 SL/TP**는 **ATR 배수**(`atrSLx`, `atrTPx`).
  - **TP1 스케일아웃**은 `tp1RR` R‑배수 도달 시, 체결되면 SL을 **BE(+ticks)**로 승격.
  - **ATR 트레일링**은 `trailRR` 이후 `atrTrailx` 배수로 추적.
  - **하드 TP**(세이프티) 유지 가능.
  - **최대 보유시간**(바 수) 초과 시 강제 청산.
- **알림:**
  - **진입 JSON**(`BULL-LONG-<timenow>`)은 상위 `entry/sl/tp`와 **`comment` 객체**에 동일 정보(중복) 포함.
  - **TP1 JSON**(`BULL-TP1-<timenow>`)은 `reduceOnly: true` + `qtyPct`와 의미 있는 `comment`(`{kind:"tp1", ...}`)를 포함.

전략은 **신호 생성/의도 인코딩**에 초점을 두고, 릴레이는 **보안 집행**과 **거래소별 세부 구현**을 담당합니다.

---

## TradingView 알림 설정

1. 차트에 전략 추가 → 파라미터 조정
2. **Create Alert** → Condition: `Any alert() function call` (본 전략은 `alert()`로 JSON을 보냅니다)
3. **Webhook URL**: `https://<your-relay>/webhook`
4. 알림은 스크립트에서 생성하는 JSON(예: `longJson`, `tp1Json`)을 그대로 전송합니다 (메시지 란은 비워도 됨)

---

## 웹훅 JSON 예시

**진입(Entry)** — Binance 기준 예시

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

**TP1(부분청산)**

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

> Phemex를 사용할 경우 `symbol`을 `PHEMEX:ETHUSDT.P`로 보내면 됩니다. 또한 `EXCHANGE=phemex`로 설정해야 합니다.

---

## Pine 전략(논리 요약)

- **진입:** 5분 Donchian 상단 돌파 (RT-safe)
- **리스크:** ATR 기반 SL/TP (배수 조정 가능)
- **익시트(적응형):** TP1(부분청산) 도달 시 BE 승격 → 이후 ATR 트레일링
- **옵션:** 하드 TP 유지, 보유시간 초과 시 시장가 청산
- **레짐 필터:** ETH/BTC 4h EMA200 동반 상방일 때만 진입 허용(옵션)
- **알림:** Entry/TP1 JSON을 `alert()`로 웹훅 전송

---
![strategy](https://github.com/user-attachments/assets/32ff6646-5fd2-47ec-8b18-1c89aa9d63f6)
![Profitable trades](https://github.com/user-attachments/assets/d70deaab-643d-4ab1-84d0-2359b135cc6d)

1 ETH 기준
- Total P&L   : +2.39% x Reverage (relay 서버는 기본으로 5배) = +11.95%
- 수익성 거래   : 67.05%
## 전체 Pine 스크립트

> 파일로도 제공: [`pine/BULL_ETH_Donchian_ATR_v4.pine`](./pine/BULL_ETH_Donchian_ATR_v4.pine)

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

## 보안/운영 권장

- HTTPS 필수(Let's Encrypt 권장), 강력한 `RELAY_SHARED_SECRET`
- 키/시크릿은 환경 변수로만 관리 (레포에 커밋 금지)
- 심볼 허용 목록·최소 수량 검증·멱등성(id 중복 처리)
- 테스트넷/페이퍼 트레이드로 충분히 검증 후 라이브 전환

---

## 🧪 로컬 테스트

간단히 `curl`로 릴레이를 점검하세요.

```bash
# 1) 헬스체크(노출 시)
curl -i http://localhost:80/health

# 2) 진입 알림 시뮬레이션
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

> 무위험 테스트를 원하면 `PHEMEX_BASE_URL`을 **testnet**으로 지정하세요.

---

## 🔐 보안 체크리스트

- **충분히 긴 `RELAY_SHARED_SECRET`**를 사용하고 주기적으로 교체하세요.
- (선택) Nginx에서 **TradingView IP 허용 목록**을 적용하거나, 프라이빗 네트워크 뒤에 배치하세요.
- 여러 전략을 운영한다면 **전략별 시크릿**도 고려하세요.
- **심볼 허용 목록**과 **최소/최대 수량 가드** 등 서버단 안전장치를 적용하세요.

---

## 📦 배포 노트

- **Dockerfile**로 Python 앱을 빌드하고, **docker‑compose**로 Nginx ↔ App, `.env` 마운트를 구성합니다.
- TradingView/Phemex와 가까운 리전을 선택하면 지연이 줄어듭니다.
- 로그/메트릭(요청 지연, 오류율, 주문 ACK 시간 등)을 모니터링하세요.

---

## ❓FAQ

**Q. 왜 `entry/sl/tp`를 상위와 `comment`에 중복하나요?**  
A. 일부 누락·문자열화 상황에서도 견고하도록 **중복**합니다. 서버는 보통 `comment` 객체를 우선 사용하되, 상위 필드를 **폴백**으로 활용할 수 있습니다.

**Q. 부분청산은 어떻게 하나요?**  
A. `action:"sell"`, `reduceOnly:true`, `qtyPct:<1..100>`를 보냅니다. 릴레이는 Phemex의 **reduce‑only** 주문으로 변환하여 순포지션이 증가하지 않도록 보장합니다.

**Q. 시장가 vs 지정가?**  
A. 기본은 시장가입니다. `orderType:"limit"`(또는 `type:"limit"`)과 `price`를 함께 보내면 지정가 주문으로 처리합니다. 생략 시 시장가로 간주하고 `price`는 로깅/메타로 사용됩니다.

---

## 📝 라이선스

MIT
