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

MIT (또는 원하는 라이선스).
