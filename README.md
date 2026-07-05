# BTC Options Straddle Dashboard

A real-time monitor for BTC option straddles on Delta Exchange: live Call LTP,
Put LTP, and the derived Straddle price (Call + Put) across every strike in
the nearest expiry, plus a candlestick chart of how any one strike's straddle
has moved over time.

This is a **read-only market-data viewer**. It never touches Delta Exchange
credentials or order-placement endpoints.

## What it does

- Tracks the full call/put chain for BTC's nearest options expiry (26 strikes)
  and streams live LTP updates for both legs of every strike.
- Computes the straddle price (`call_ltp + put_ltp`) server-side as soon as
  both legs of a strike are known.
- Renders a live table (Call LTP / Put LTP / Strike / Straddle), sortable and
  searchable, that only repaints the row that actually changed on each tick.
- Logs every straddle tick per strike and turns that log into OHLC candles
  (1m / 5m / 15m / 1h) on a second "Straddle Chart" tab, with a strike
  dropdown and a TradingView `lightweight-charts` candlestick series.
- Survives page refreshes: tick history is persisted to IndexedDB, and the
  WebSocket reconnects with backoff if the connection drops.

## Architecture

Three tiers, two independent WebSocket hops:

```
Delta Exchange (public REST + WS, no API key required)
        │  wss:// v2/ticker — per-symbol LTP stream, subscribed once
        │  per call/put symbol in the chain + the BTC spot index
        ▼
Backend — FastAPI (Python), single process           [backend/]
   DeltaOptionsStreamer  owns the Delta connection: resolves the nearest
                         expiry, subscribes every symbol, parses each tick,
                         updates OptionStore, broadcasts single-row diffs.
                         Reconnects with exponential backoff (1s→30s) on drop.
   OptionStore           in-memory strike → row map; the single source of
                         truth server-side. Mutated in place on the asyncio
                         loop, so no locking is needed.
   ConnectionManager     tracks connected browser tabs, deliberately
                         decoupled from the upstream Delta connection — a
                         tab reconnecting can never cascade into Delta.
        │  ws://…/ws — JSON: a full snapshot on connect, then one
        │  row-update / spot-update / status message per change
        ▼
Frontend — React 19 + Vite (TypeScript)               [frontend/]
   socket.ts             the one WebSocket client; fans each frame out to
                         both stores below. Reconnects with its own backoff.
   optionStore.ts        client mirror of the table state. Rows are
                         *replaced*, not mutated, so React only re-renders
                         the one row that changed.
   tickStore.ts          rolling 24h tick log per strike (in-memory +
                         batched IndexedDB writes), decoupled from the UI.
   candleBuilder.ts       pure, unit-tested function: buckets ticks into
                         clock-aligned OHLC candles per timeframe, carrying
                         the last close forward through silent buckets.
   Options Table         virtualized (@tanstack/react-virtual), one
                         subscription per row.
   Straddle Chart        strike dropdown + timeframe toggle +
                         lightweight-charts candlestick series, themed
                         from the app's own CSS variables.
```

### One tick's lifecycle

1. Delta's public WS pushes a `v2/ticker` frame for one option symbol
   (e.g. `C-BTC-95000-050726`).
2. `DeltaOptionsStreamer` parses the symbol into (call/put, strike) and
   updates that strike's row in `OptionStore`.
3. Once both legs of the strike are known, the backend computes the
   straddle and broadcasts a single-row `RowUpdateMessage` to every
   connected tab.
4. `socket.ts` hands the message to **both** `optionStore.dispatch()` (table)
   and `tickStore.ingest()` (chart tick log), in parallel.
5. The table re-renders only the one row subscribed to that strike.
6. `tickStore` appends the tick to that strike's rolling buffer, evicts
   anything older than 24h, and queues it for a batched IndexedDB write.
7. If the Straddle Chart tab is open on that strike, `useStraddleCandles`
   reruns `buildCandles()` and the still-forming candle updates live.

## Project structure

```
backend/
  config.py                 env-driven settings (Delta URLs, CORS, backoff)
  models/option_row.py      OptionRow dataclass (call/put LTP, derived straddle)
  schemas/ws_messages.py     pydantic WS message contracts
  services/
    option_store.py         in-memory strike -> row map
    expiry_service.py       resolves the nearest BTC options expiry
    delta_rest.py           one-shot REST seed calls (ticker snapshot, spot price)
  websocket/
    delta_client.py         DeltaOptionsStreamer — the core streaming engine
    manager.py              ConnectionManager for connected browser tabs
    endpoints.py            the /ws route
  api/routes.py             /api/health, /api/option-chain (REST debug mirror)
  main.py                   FastAPI app wiring

frontend/
  src/
    services/socket.ts       WebSocket client, fans out to both stores
    services/optionStore.ts  client-side table state (pub/sub)
    lib/tickStore.ts         tick ingestion + IndexedDB persistence
    lib/candleBuilder.ts     pure OHLC bucketing logic (unit tested)
    hooks/                   useOptionRow, useStrikeList, useHeaderStats,
                              useStraddleCandles — useSyncExternalStore adapters
    components/
      OptionsTable.tsx        virtualized live table
      StraddleChart.tsx       candlestick chart tab
    pages/Dashboard.tsx       tab bar + page composition
```

## Running it

**Backend** (Python 3.12+):

```
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend** (Node 18+):

```
cd frontend
npm install
npm run dev
```

The frontend defaults to `ws://<host>:8000/ws`; override with `VITE_WS_URL`
if the backend runs elsewhere. Backend config is env-driven via
`STRADDLE_*` variables — see `backend/.env.example`.

## Testing

```
cd frontend
npm run test    # vitest — candleBuilder + tickStore unit tests
```

## Design decisions worth knowing

- **Diffs, not snapshots.** After the initial connect, every update — both
  backend→frontend and inside the frontend's own store — is a single-row
  message. Cost scales with market activity, not with strike count.
- **Two independently self-healing WebSocket hops.** Backend↔Delta and
  browser↔backend each reconnect on their own with exponential backoff, so
  a browser tab's connection churn can never affect the upstream Delta feed.
- **The tick logger hooks in at the edge, not the core.** `tickStore.ingest()`
  is called from `socket.ts` right next to the existing `optionStore.dispatch()`
  call — the candlestick feature was added without changing a single line
  inside `optionStore.ts` or the table's rendering path.
- **IndexedDB over localStorage for tick history.** Tens of thousands of
  ticks/day across 26 strikes would mean synchronous, string-serialized
  writes blocking the main thread with localStorage. IndexedDB is async,
  scales comfortably, and its timestamp index turns the 24h eviction sweep
  into a cheap range-delete.
- **Silent buckets carry the last close forward.** A strike that goes quiet
  for a few minutes gets flat candles, not a gap in the chart — the same
  convention TradingView/Zerodha-style charts use for thin option liquidity.

## Stack

- **Backend:** Python 3.12, FastAPI, uvicorn, `websockets`, `httpx`, pydantic v2
- **Frontend:** React 19, Vite 8, TypeScript, Tailwind CSS v4,
  `@tanstack/react-virtual`, `lightweight-charts` 5, vitest
- **External:** Delta Exchange India public REST (`api.india.delta.exchange`)
  and public WebSocket (`socket.india.delta.exchange`) — no API key required

## Known follow-up (not built)

Delta Exchange exposes `GET /v2/candles`, a public REST endpoint for
historical OHLC data (symbol/resolution/time-range params). The chart
currently only accumulates candles from ticks seen since the app started;
backfilling from that endpoint is possible later but out of scope for now.
