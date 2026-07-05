import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router as api_router
from config import settings
from services.option_store import OptionStore
from websocket.delta_client import DeltaOptionsStreamer
from websocket.endpoints import router as ws_router
from websocket.manager import ConnectionManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(app.state.streamer.run_forever())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="BTC Options Straddle Dashboard API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.store = OptionStore()
app.state.manager = ConnectionManager()
app.state.streamer = DeltaOptionsStreamer(app.state.store, app.state.manager)

app.include_router(api_router)
app.include_router(ws_router)
