"""Product Service API - FastAPI microservice for product management."""

from typing import Annotated
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from redis_om import get_redis_connection, HashModel
from redis import Redis
from pydantic import BaseModel, Field, ConfigDict

from env import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD


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
class Product(HashModel):
    """Product model for Redis OM."""

    name: str = Field(..., description="Product name")
    price: float = Field(..., gt=0, description="Product price (must be positive)")
    quantity: int = Field(..., ge=0, description="Available quantity (non-negative)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Sample Product",
                "price": 29.99,
                "quantity": 100,
            }
        }
    )

    class Meta:
        database = redis


# API request/response models
class ProductCreate(BaseModel):
    """Schema for creating a new product."""

    name: str = Field(..., min_length=1, max_length=200, description="Product name")
    price: float = Field(..., gt=0, description="Product price (must be positive)")
    quantity: int = Field(..., ge=0, description="Available quantity (non-negative)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Sample Product",
                "price": 29.99,
                "quantity": 100,
            }
        }
    )


class ProductResponse(BaseModel):
    """Schema for product response."""

    id: str = Field(..., description="Product unique identifier")
    name: str = Field(..., description="Product name")
    price: float = Field(..., description="Product price")
    quantity: int = Field(..., description="Available quantity")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "01HXQK3J5N8V9QW7E6R5T4Y3Z2",
                "name": "Sample Product",
                "price": 29.99,
                "quantity": 100,
            }
        }
    )


# Lifespan context manager for startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events."""
    # Startup: could add connection pooling, logging setup, etc.
    yield
    # Shutdown: cleanup resources if needed


# Initialize FastAPI app
app = FastAPI(
    title="Product Service API",
    description="Microservice for managing product inventory",
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


def format_product(pk: str) -> ProductResponse:
    """Format a product from Redis to API response model.

    Args:
        pk: Product primary key

    Returns:
        ProductResponse: Formatted product data

    Raises:
        HTTPException: If product not found
    """
    try:
        product = Product.get(pk)
        return ProductResponse(
            id=product.pk,
            name=product.name,
            price=product.price,
            quantity=product.quantity,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id '{pk}' not found",
        ) from e


@app.get(
    "/products",
    response_model=list[ProductResponse],
    status_code=status.HTTP_200_OK,
    summary="Get all products",
    description="Retrieve a list of all products in the inventory",
)
async def get_all_products() -> list[ProductResponse]:
    """Get all products from the inventory.

    Returns:
        list[ProductResponse]: List of all products
    """
    return [format_product(pk) for pk in Product.all_pks()]


@app.post(
    "/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new product",
    description="Add a new product to the inventory",
)
async def create_product(product: ProductCreate) -> ProductResponse:
    """Create a new product in the inventory.

    Args:
        product: Product data to create

    Returns:
        ProductResponse: Created product data
    """
    db_product = Product(**product.model_dump())
    db_product.save()

    return ProductResponse(
        id=db_product.pk,
        name=db_product.name,
        price=db_product.price,
        quantity=db_product.quantity,
    )


@app.get(
    "/products/{pk}",
    response_model=ProductResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a product by ID",
    description="Retrieve a single product by its unique identifier",
)
async def get_product(pk: str) -> ProductResponse:
    """Get a single product by ID.

    Args:
        pk: Product unique identifier

    Returns:
        ProductResponse: Product data

    Raises:
        HTTPException: If product not found
    """
    return format_product(pk)


@app.delete(
    "/products/{pk}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a product",
    description="Remove a product from the inventory by its ID",
)
async def delete_product(pk: str) -> None:
    """Delete a product from the inventory.

    Args:
        pk: Product unique identifier

    Raises:
        HTTPException: If product not found or deletion fails
    """
    try:
        result = Product.delete(pk)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with id '{pk}' not found",
            )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete product",
        ) from e
