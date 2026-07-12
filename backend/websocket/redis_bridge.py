import logging

from services.message_bus import RedisSubscriber
from websocket.manager import ConnectionManager

logger = logging.getLogger(__name__)


class RedisBroadcastBridge:
    """Subscribes to the channel the Market Data Service publishes to, and
    re-broadcasts every message to this gateway's locally connected clients
    via ConnectionManager.

    This is the decoupling point: the Market Data Service (DeltaOptionsStreamer)
    publishes once and knows nothing about ConnectionManager or how many
    gateway instances exist. Any number of gateway processes, each running
    its own bridge, receive every message independently.
    """

    def __init__(self, subscriber: RedisSubscriber, manager: ConnectionManager) -> None:
        self.subscriber = subscriber
        self.manager = manager

    async def run_forever(self) -> None:
        await self.subscriber.connect()
        async for message in self.subscriber.listen():
            await self.manager.broadcast(message)
