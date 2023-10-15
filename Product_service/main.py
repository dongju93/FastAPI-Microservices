from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis_om import get_redis_connection, HashModel
from pydantic import BaseModel
from env import *


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

redis = get_redis_connection(
    host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, decode_responses=True
)


# Database model
class Product(HashModel):
    name: str
    price: float
    quantity: int

    class Meta:
        database = redis


# API model
class ProductAPI(BaseModel):
    name: str
    price: float
    quantity: int


# Get all items
@app.get("/products")
def all():
    return [format(pk) for pk in Product.all_pks()]


def format(pk: str):
    product = Product.get(pk)

    return {
        "id": product.pk,
        "name": product.name,
        "price": product.price,
        "quantity": product.quantity,
    }


# Add item
@app.post("/products")
def create(product: ProductAPI):
    db_product = Product(**product.dict())
    db_product.save()
    return db_product.dict()


# Get single item
@app.get("/products/{pk}")
def get(pk: str):
    return Product.get(pk)


# Delete item
@app.delete("/products/{pk}")
def delete(pk: str):
    return Product.delete(pk)
