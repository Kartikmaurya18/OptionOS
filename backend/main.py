import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router as api_router
from config import settings
from services.message_bus import RedisPublisher, RedisSubscriber
from services.option_store import OptionStore
from websocket.delta_client import DeltaOptionsStreamer
from websocket.endpoints import router as ws_router
from websocket.manager import ConnectionManager
from websocket.redis_bridge import RedisBroadcastBridge

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await app.state.publisher.connect()
    bridge_task = asyncio.create_task(app.state.redis_bridge.run_forever())
    # One DeltaOptionsStreamer task per configured asset -- a reconnect
    # storm on one asset's Delta feed never blocks or delays another's.
    streamer_tasks = [asyncio.create_task(streamer.run_forever()) for streamer in app.state.streamers.values()]
    try:
        yield
    finally:
        for task in streamer_tasks:
            task.cancel()
        bridge_task.cancel()
        await app.state.publisher.close()


app = FastAPI(title="Options Market Data Platform API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.manager = ConnectionManager()
app.state.publisher = RedisPublisher(settings.redis_url, settings.redis_channel)
app.state.stores = {asset: OptionStore() for asset in settings.assets}
app.state.streamers = {
    asset: DeltaOptionsStreamer(asset, app.state.stores[asset], app.state.publisher) for asset in settings.assets
}
app.state.redis_bridge = RedisBroadcastBridge(
    RedisSubscriber(settings.redis_url, settings.redis_channel), app.state.manager
)

app.include_router(api_router)
app.include_router(ws_router)
