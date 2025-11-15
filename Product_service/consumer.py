"""Redis Stream Consumer for Product Service - Handles order completion events."""

import logging
import time
from typing import Any

from redis import Redis
from redis.exceptions import ResponseError, ConnectionError as RedisConnectionError

from main import redis, Product

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Redis Stream configuration
STREAM_KEY: str = "order_completed"
CONSUMER_GROUP: str = "inventory-group"
CONSUMER_NAME: str = "inventory-consumer-1"
REFUND_STREAM_KEY: str = "refund_order"
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


def process_order_completion(redis_client: Redis, order_data: dict[str, Any]) -> None:
    """Process an order completion event and update product inventory.

    Args:
        redis_client: Redis client instance
        order_data: Order data from the stream event

    Raises:
        Exception: If product update fails
    """
    product_id: str = order_data.get("product_id", "")
    quantity_str: str = order_data.get("quantity", "0")

    try:
        quantity: int = int(quantity_str)
        product = Product.get(product_id)

        # Update product quantity
        new_quantity = product.quantity - quantity

        if new_quantity < 0:
            logger.warning(
                f"Insufficient inventory for product {product_id}. "
                f"Available: {product.quantity}, Requested: {quantity}"
            )
            # Trigger refund event
            redis_client.xadd(REFUND_STREAM_KEY, order_data, "*")
            logger.info(f"Refund event created for order with product_id: {product_id}")
        else:
            product.quantity = new_quantity
            product.save()
            logger.info(
                f"Updated product {product_id}: quantity {product.quantity + quantity} -> {product.quantity}"
            )

    except ValueError as e:
        logger.error(f"Invalid quantity value '{quantity_str}': {e}")
        # Trigger refund for invalid data
        redis_client.xadd(REFUND_STREAM_KEY, order_data, "*")
    except Exception as e:
        logger.error(f"Failed to process order for product {product_id}: {e}")
        # Trigger refund event on failure
        redis_client.xadd(REFUND_STREAM_KEY, order_data, "*")
        logger.info(f"Refund event created due to processing error for product_id: {product_id}")


def consume_order_events() -> None:
    """Main consumer loop to process order completion events from Redis Stream."""
    logger.info("Starting Product Service consumer...")

    # Create consumer group
    create_consumer_group(redis, STREAM_KEY, CONSUMER_GROUP)

    logger.info(f"Listening for events on stream '{STREAM_KEY}'...")

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
                        logger.info(f"Processing message {message_id}: {message_data}")

                        try:
                            process_order_completion(redis, message_data)
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
    consume_order_events()
