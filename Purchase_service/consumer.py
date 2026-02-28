"""Redis Stream Consumer for Purchase Service - Handles refund events."""

import logging
import time
from typing import Any

from redis import Redis
from redis.exceptions import ResponseError, ConnectionError as RedisConnectionError

from main import redis, Order

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Redis Stream configuration
STREAM_KEY: str = "refund_order"
CONSUMER_GROUP: str = "payment-group"
CONSUMER_NAME: str = "payment-consumer-1"
POLL_INTERVAL_SECONDS: int = 1


def create_consumer_group(redis_client: Redis, key: str, group: str) -> None:
    """Create a Redis consumer group if it doesn't exist.

    Args:
        redis_client: Redis client instance
        key: Stream key name
        group: Consumer group name
    """
    try:
        redis_client.xgroup_create(key, group, mkstream=True)
        logger.info(f"Created consumer group '{group}' for stream '{key}'")
    except ResponseError as e:
        if "BUSYGROUP" in str(e):
            logger.info(f"Consumer group '{group}' already exists for stream '{key}'")
        else:
            logger.error(f"Error creating consumer group: {e}")
            raise


def process_refund_event(redis_client: Redis, refund_data: dict[str, Any]) -> None:
    """Process a refund event and update order status.

    Args:
        redis_client: Redis client instance
        refund_data: Refund data from the stream event

    Raises:
        Exception: If order update fails
    """
    order_pk: str = refund_data.get("pk", "")

    if not order_pk:
        logger.error(f"Invalid refund event - missing 'pk' field: {refund_data}")
        return

    try:
        # Get the order and update status to refunded
        order = Order.get(order_pk)
        previous_status = order.status
        order.status = "refunded"
        order.save()

        logger.info(
            f"Refunded order {order_pk}: status changed from '{previous_status}' to 'refunded'"
        )

    except Exception as e:
        logger.error(f"Failed to process refund for order {order_pk}: {e}")
        raise


def consume_refund_events() -> None:
    """Main consumer loop to process refund events from Redis Stream."""
    logger.info("Starting Purchase Service consumer...")

    # Create consumer group
    create_consumer_group(redis, STREAM_KEY, CONSUMER_GROUP)

    logger.info(f"Listening for refund events on stream '{STREAM_KEY}'...")

    while True:
        try:
            # Read from stream with consumer group
            results = redis.xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=CONSUMER_NAME,
                streams={STREAM_KEY: ">"},
                count=10,  # Process up to 10 messages at a time
                block=2000,  # Block for 2 seconds waiting for messages
            )

            if results:
                for stream_name, messages in results:
                    for message_id, message_data in messages:
                        logger.info(f"Processing refund message {message_id}: {message_data}")

                        try:
                            process_refund_event(redis, message_data)
                            # Acknowledge the message
                            redis.xack(STREAM_KEY, CONSUMER_GROUP, message_id)
                            logger.info(f"Acknowledged message {message_id}")
                        except Exception as e:
                            logger.error(f"Error processing message {message_id}: {e}")
                            # Message will not be acknowledged and can be reprocessed

        except RedisConnectionError as e:
            logger.error(f"Redis connection error: {e}")
            logger.info(f"Retrying in {POLL_INTERVAL_SECONDS * 5} seconds...")
            time.sleep(POLL_INTERVAL_SECONDS * 5)
        except Exception as e:
            logger.error(f"Unexpected error in consumer loop: {e}")
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    consume_refund_events()
