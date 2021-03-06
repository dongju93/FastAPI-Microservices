from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.background import BackgroundTasks
from redis_om import get_redis_connection, HashModel
from starlette.requests import Request
import requests, time
from env import *

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:3000'],
    allow_methods=['*'],
    allow_headers=['*']
)

# this should be a different database but, free plan doesn't ๐ฅฒ
redis = get_redis_connection(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    decode_responses=True
)

class Order(HashModel):
    product_id: str
    price: float
    fee: float
    total: float
    quantity: int
    status: str # pending, completed, refunded

    class Meta:
        database = redis

@app.get("/orders/{pk}")
def get(pk: str): # pk๋ order์ ์์ฑ๋ ๊ณ ์  id์, ์ํ id์๋ ๋ค๋ฆ
    return Order.get(pk)

@app.post("/orders")
async def create(request: Request, background_tasks: BackgroundTasks): # id, quantity
    body = await request.json()

    req = requests.get('http://localhost:8000/products/%s' % body['id']) # %s: str
    product = req.json()

    order = Order(
        product_id=body['id'], # request ํ id
        price=product['price'],
        fee=0.2 * product['price'], # ์์๋ฃ
        total=1.2 * product['price'], # ๋ง์ง
        quantity=body['quantity'], # request ํ ์๋
        status='pending' # ์ฃผ๋ฌธ ์ฆ์ ์ํ ๊ธฐ๋ณธ๊ฐ
    )
    order.save()
    # Order save๊ฐ error ์์ด ์๋ฃ ์ ๋ฐฑ๊ทธ๋ผ์ด๋์์ ์ฃผ๋ฌธ์ํ ๋ณ๊ฒฝ def ์ํ
    background_tasks.add_task(order_completed, order)

    return order

def order_completed(order: Order):
    time.sleep(5) # ์๋์  5์ด ์ง์ฐ
    order.status = 'completed'
    order.save()
    # Redis stream event
    redis.xadd('order_completed', order.dict(), '*')
