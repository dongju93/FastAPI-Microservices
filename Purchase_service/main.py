"""Purchase Service API - FastAPI microservice for order management."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import FastAPI, HTTPException, BackgroundTasks, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from redis import Redis
from redis_om import get_redis_connection, HashModel

from env import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Product service configuration
PRODUCT_SERVICE_URL: str = "http://localhost:8000"


# Dependency injection for Redis connection
def get_redis() -> Redis:
    """Get Redis connection instance.

    Returns:
        Redis: Redis connection instance with decode_responses=True
    """
    return get_redis_connection(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        decode_responses=True,
    )


# Initialize Redis connection for models
redis = get_redis()


# Database model
class Order(HashModel):
    """Order model for Redis OM."""

    product_id: str = Field(..., description="Product unique identifier")
    price: float = Field(..., gt=0, description="Product price")
    fee: float = Field(..., ge=0, description="Service fee")
    total: float = Field(..., gt=0, description="Total amount")
    quantity: int = Field(..., gt=0, description="Order quantity")
    status: str = Field(
        default="pending",
        description="Order status: pending, completed, or refunded",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "product_id": "01HXQK3J5N8V9QW7E6R5T4Y3Z2",
                "price": 29.99,
                "fee": 5.99,
                "total": 35.98,
                "quantity": 1,
                "status": "pending",
            }
        }
    )

    class Meta:
        database = redis


# API request/response models
class OrderCreate(BaseModel):
    """Schema for creating a new order."""

    id: str = Field(..., description="Product ID to order")
    quantity: int = Field(..., gt=0, description="Quantity to order (must be positive)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "01HXQK3J5N8V9QW7E6R5T4Y3Z2",
                "quantity": 2,
            }
        }
    )


class OrderResponse(BaseModel):
    """Schema for order response."""

    pk: str = Field(..., description="Order unique identifier")
    product_id: str = Field(..., description="Product unique identifier")
    price: float = Field(..., description="Product price")
    fee: float = Field(..., description="Service fee")
    total: float = Field(..., description="Total amount")
    quantity: int = Field(..., description="Order quantity")
    status: str = Field(..., description="Order status")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "pk": "01HXQK3J5N8V9QW7E6R5T4Y3Z2",
                "product_id": "01HXQK3J5N8V9QW7E6R5T4Y3Z2",
                "price": 29.99,
                "fee": 5.99,
                "total": 35.98,
                "quantity": 2,
                "status": "pending",
            }
        }
    )


class ProductResponse(BaseModel):
    """Schema for product data from Product Service."""

    id: str
    name: str
    price: float
    quantity: int


# Lifespan context manager for startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events."""
    logger.info("Starting Purchase Service...")
    yield
    logger.info("Shutting down Purchase Service...")


# Initialize FastAPI app
app = FastAPI(
    title="Purchase Service API",
    description="Microservice for managing orders and purchases",
    version="2.0.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def fetch_product(product_id: str) -> ProductResponse:
    """Fetch product details from Product Service.

    Args:
        product_id: Product unique identifier

    Returns:
        ProductResponse: Product details

    Raises:
        HTTPException: If product not found or service unavailable
    """
    url = f"{PRODUCT_SERVICE_URL}/products/{product_id}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)

            if response.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Product with id '{product_id}' not found",
                )

            response.raise_for_status()
            product_data = response.json()

            return ProductResponse(**product_data)

    except httpx.TimeoutException as e:
        logger.error(f"Timeout fetching product {product_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Product service is currently unavailable",
        ) from e
    except httpx.RequestError as e:
        logger.error(f"Error fetching product {product_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to communicate with product service",
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching product {product_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred",
        ) from e


async def complete_order(order: Order) -> None:
    """Complete an order by updating status and publishing to Redis stream.

    This function runs as a background task with a simulated processing delay.

    Args:
        order: Order instance to complete
    """
    try:
        # Simulate order processing time
        await asyncio.sleep(5)

        # Update order status
        order.status = "completed"
        order.save()

        logger.info(f"Order {order.pk} completed successfully")

        # Publish order completion event to Redis stream
        redis.xadd("order_completed", order.model_dump(), "*")
        logger.info(f"Published completion event for order {order.pk}")

    except Exception as e:
        logger.error(f"Error completing order {order.pk}: {e}")
        # In production, you might want to retry or handle this differently


@app.get(
    "/orders/{pk}",
    response_model=OrderResponse,
    status_code=status.HTTP_200_OK,
    summary="Get an order by ID",
    description="Retrieve order details by its unique identifier",
)
async def get_order(pk: str) -> OrderResponse:
    """Get a single order by ID.

    Args:
        pk: Order unique identifier

    Returns:
        OrderResponse: Order details

    Raises:
        HTTPException: If order not found
    """
    try:
        order = Order.get(pk)
        return OrderResponse(
            pk=order.pk,
            product_id=order.product_id,
            price=order.price,
            fee=order.fee,
            total=order.total,
            quantity=order.quantity,
            status=order.status,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with id '{pk}' not found",
        ) from e


@app.post(
    "/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new order",
    description="Create a new order for a product. The order will be processed asynchronously.",
)
async def create_order(
    order_request: OrderCreate,
    background_tasks: BackgroundTasks,
) -> OrderResponse:
    """Create a new order.

    This endpoint:
    1. Fetches product details from the Product Service
    2. Calculates order total with fees
    3. Creates the order with 'pending' status
    4. Schedules background task to complete the order

    Args:
        order_request: Order creation request with product ID and quantity
        background_tasks: FastAPI background tasks manager

    Returns:
        OrderResponse: Created order details

    Raises:
        HTTPException: If product not found or service unavailable
    """
    # Fetch product details from Product Service
    product = await fetch_product(order_request.id)

    # Validate product availability
    if product.quantity < order_request.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient inventory. Available: {product.quantity}, Requested: {order_request.quantity}",
        )

    # Calculate order totals
    item_total = product.price * order_request.quantity
    service_fee = 0.2 * item_total  # 20% service fee
    total_amount = item_total + service_fee

    # Create order
    order = Order(
        product_id=order_request.id,
        price=product.price,
        fee=service_fee,
        total=total_amount,
        quantity=order_request.quantity,
        status="pending",
    )
    order.save()

    logger.info(
        f"Created order {order.pk} for product {order_request.id} "
        f"(quantity: {order_request.quantity}, total: {total_amount})"
    )

    # Schedule background task to complete the order
    background_tasks.add_task(complete_order, order)

    return OrderResponse(
        pk=order.pk,
        product_id=order.product_id,
        price=order.price,
        fee=order.fee,
        total=order.total,
        quantity=order.quantity,
        status=order.status,
    )
