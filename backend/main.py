import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from api.backfill import router as backfill_router
from api.routes import router as api_router
from config import settings
from services.clickhouse_store import ClickHouseStore
from services.message_bus import RedisPublisher, RedisStreamConsumer, RedisSubscriber
from services.option_store import OptionStore
from services.tick_persistence import TickPersistenceService
from websocket.delta_client import DeltaOptionsStreamer
from websocket.endpoints import router as ws_router
from websocket.manager import ConnectionManager
from websocket.redis_bridge import RedisBroadcastBridge

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await app.state.publisher.connect()
    await app.state.clickhouse.connect()

    bridge_task = asyncio.create_task(app.state.redis_bridge.run_forever())
    persistence_task = asyncio.create_task(app.state.tick_persistence.run_forever())
    # One DeltaOptionsStreamer task per configured asset -- a reconnect
    # storm on one asset's Delta feed never blocks or delays another's.
    streamer_tasks = [asyncio.create_task(streamer.run_forever()) for streamer in app.state.streamers.values()]
    try:
        yield
    finally:
        for task in streamer_tasks:
            task.cancel()
        bridge_task.cancel()
        persistence_task.cancel()
        await app.state.publisher.close()
        await app.state.clickhouse.close()


app = FastAPI(title="Options Market Data Platform API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.manager = ConnectionManager()
app.state.publisher = RedisPublisher(
    settings.redis_url, settings.redis_channel, settings.redis_stream_key, settings.redis_stream_maxlen
)
app.state.stores = {asset: OptionStore() for asset in settings.assets}
app.state.streamers = {
    asset: DeltaOptionsStreamer(asset, app.state.stores[asset], app.state.publisher) for asset in settings.assets
}
app.state.redis_bridge = RedisBroadcastBridge(
    RedisSubscriber(settings.redis_url, settings.redis_channel), app.state.manager
)

app.state.clickhouse = ClickHouseStore()
app.state.tick_persistence = TickPersistenceService(
    RedisStreamConsumer(
        settings.redis_url,
        settings.redis_stream_key,
        group="tick-writers",
        # Unique per process so restarting the backend doesn't collide with
        # a still-registered-but-dead consumer name in the same group; the
        # group itself (not the consumer name) is what makes delivery
        # exactly-once-collectively across however many of these run.
        consumer_name=f"tick-persistence-{uuid.uuid4().hex[:8]}",
    ),
    app.state.clickhouse,
)

app.include_router(api_router)
app.include_router(ws_router)
app.include_router(backfill_router)

# Prometheus scrapes this with a plain GET -- no auth, no framing, just
# text. make_asgi_app() is a tiny self-contained ASGI app that reads the
# global registry every metric in observability/metrics.py registered
# itself into, and renders it in Prometheus's text exposition format.
app.mount("/metrics", make_asgi_app())
