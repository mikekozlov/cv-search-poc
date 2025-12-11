import json
import os
import threading
import time
from collections import defaultdict, deque
from typing import Any, Callable, Optional, Sequence

import redis


class _InMemoryPubSub:
    """Minimal pubsub stub to satisfy tests when using the in-memory backend."""

    def subscribe(self, channel: str) -> None:
        self.channel = channel

    def listen(self):
        return iter(())


class _InMemoryRedis:
    """Lightweight in-memory stand-in for redis-py used in tests."""

    def __init__(self):
        self._queues: dict[str, deque[str]] = defaultdict(deque)
        self._cv = threading.Condition()

    def ping(self):
        return True

    def rpush(self, name: str, value: str):
        with self._cv:
            self._queues[name].append(value)
            self._cv.notify_all()
            return len(self._queues[name])

    def blpop(self, name: str, timeout: int = 0):
        deadline = None if not timeout else time.time() + timeout
        with self._cv:
            while not self._queues[name]:
                if deadline is None:
                    self._cv.wait()
                    continue
                remaining = deadline - time.time()
                if remaining <= 0:
                    return None
                self._cv.wait(timeout=remaining)
            value = self._queues[name].popleft()
            return name, value

    def delete(self, *names):
        with self._cv:
            for queue_name in names:
                self._queues.pop(queue_name, None)

    def llen(self, name: str):
        with self._cv:
            return len(self._queues.get(name, ()))

    def flushdb(self):
        with self._cv:
            self._queues.clear()

    def close(self):
        return None

    def publish(self, channel: str, message: str):
        return 0

    def pubsub(self):
        return _InMemoryPubSub()


class RedisClient:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        redis_url: str | None = None,
    ):
        default_url = redis_url or os.getenv("REDIS_URL", f"redis://{host}:{port}/{db}")
        self.redis_url = default_url
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

    def clear_queues(self, names: Sequence[str]) -> None:
        """Delete the provided Redis list keys; safe if keys are missing."""
        if not names:
            return
        self.client.delete(*names)

    def close(self) -> None:
        """Close the underlying Redis connection pool."""
        try:
            self.client.close()
        except Exception:
            # Closing failures should not block tests or shutdown paths.
            pass


class InMemoryRedisClient(RedisClient):
    """Drop-in RedisClient replacement backed by an in-memory queue store."""

    def __init__(self):
        self.redis_url = "memory://"
        self.client = _InMemoryRedis()
