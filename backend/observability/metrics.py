"""Prometheus metrics for the backend.

Every metric here registers itself into prometheus_client's default global
registry the moment this module is imported -- that's what main.py's
/metrics endpoint (via prometheus_client.make_asgi_app()) reads from. There's
one registry for the whole process, shared across Market Data Service,
WebSocket Gateway, TickPersistenceService, and HistoricalBackfillService,
since all four are still co-located in this one FastAPI app for now (see
Part 9 of the architecture doc for the eventual physical split -- each
service would get this same module, its own registry, its own /metrics).

Three metric types are used here, each answering a different question:
  - Counter: "how many times has X happened, ever?" Only goes up. Useful
    for computing a *rate* (e.g. ticks/sec = derivative of the counter).
  - Gauge: "what is X right now?" Can go up or down. Useful for point-in-
    time state like connection counts.
  - Histogram: "how long did X take, distributed how?" Buckets
    observations so Prometheus/Grafana can compute percentiles (p50/p95/
    p99) later -- a plain average would hide a slow tail.
"""

from prometheus_client import Counter, Gauge, Histogram

ticks_ingested_total = Counter(
    "ticks_ingested_total",
    "Ticks received from Delta Exchange and applied to an OptionStore row.",
    ["asset"],
)

tick_to_publish_seconds = Histogram(
    "tick_to_publish_seconds",
    "Time from receiving a raw Delta WS frame to publishing the derived update onto Redis.",
    ["asset"],
    buckets=(0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

delta_reconnects_total = Counter(
    "delta_reconnects_total",
    "Times the upstream Delta Exchange WebSocket connection was lost and reconnected.",
    ["asset"],
)

option_store_row_count = Gauge(
    "option_store_row_count",
    "Strikes currently tracked in this asset's OptionStore.",
    ["asset"],
)

candle_engine_active_keys = Gauge(
    "candle_engine_active_keys",
    "Active (instrument, timeframe) candles currently held in memory for this asset.",
    ["asset"],
)

gateway_connected_clients = Gauge(
    "gateway_connected_clients",
    "Browser WebSocket connections currently held by this gateway process.",
)

gateway_dropped_sends_total = Counter(
    "gateway_dropped_sends_total",
    "Client sends that failed (stale/broken socket), causing that client to be dropped.",
)

tick_persistence_batch_size = Histogram(
    "tick_persistence_batch_written_size",
    "Number of stream entries written to ClickHouse per batch.",
    buckets=(1, 5, 10, 25, 50, 100, 250, 500),
)

tick_persistence_write_errors_total = Counter(
    "tick_persistence_write_errors_total",
    "Batches that failed to write to ClickHouse and were left unacked for redelivery.",
)

backfill_query_seconds = Histogram(
    "backfill_query_seconds",
    "Time to serve a /api/candles backfill request, from request to response.",
    ["asset"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)
