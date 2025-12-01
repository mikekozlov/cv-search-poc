import os
import redis
import json
from typing import Any, Callable, Optional

class RedisClient:
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        self.redis_url = os.getenv("REDIS_URL", f"redis://{host}:{port}/{db}")
        self.client = redis.from_url(self.redis_url, decode_responses=True)

    def publish(self, channel: str, message: dict[str, Any]):
        """Publish a JSON message to a channel."""
        self.client.publish(channel, json.dumps(message))

    def subscribe(self, channel: str, callback: Callable[[dict[str, Any]], None]):
        """Subscribe to a channel and process messages with a callback."""
        pubsub = self.client.pubsub()
        pubsub.subscribe(channel)
        print(f"Subscribed to {channel}...")
        
        for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    callback(data)
                except json.JSONDecodeError:
                    print(f"Failed to decode message: {message['data']}")
                except Exception as e:
                    print(f"Error processing message: {e}")

    def push_to_queue(self, queue_name: str, message: dict[str, Any]):
        """Push a message to a list (queue)."""
        self.client.rpush(queue_name, json.dumps(message))

    def pop_from_queue(self, queue_name: str, timeout: int = 0) -> Optional[dict[str, Any]]:
        """Blocking pop from a list (queue)."""
        result = self.client.blpop(queue_name, timeout=timeout)
        if result:
            _, data = result
            return json.loads(data)
        return None
