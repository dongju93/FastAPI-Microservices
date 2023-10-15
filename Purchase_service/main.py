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
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# this should be a different database but, free plan doesn't 🥲
redis = get_redis_connection(
    host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, decode_responses=True
)


class Order(HashModel):
    product_id: str
    price: float
    fee: float
    total: float
    quantity: int
    status: str  # pending, completed, refunded

    class Meta:
        database = redis


@app.get("/orders/{pk}")
def get(pk: str):  # pk는 order시 생성된 고유 id임, 상품 id와는 다름
    return Order.get(pk)


@app.post("/orders")
async def create(request: Request, background_tasks: BackgroundTasks):  # id, quantity
    body = await request.json()

    req = requests.get("http://localhost:8000/products/%s" % body["id"])  # %s: str
    product = req.json()

    order = Order(
        product_id=body["id"],  # request 한 id
        price=product["price"],
        fee=0.2 * product["price"],  # 수수료
        total=1.2 * product["price"],  # 마진
        quantity=body["quantity"],  # request 한 수량
        status="pending",  # 주문 즉시 상태 기본값
    )
    order.save()
    # Order save가 error 없이 완료 시 백그라운드에서 주문상태 변경 def 수행
    background_tasks.add_task(order_completed, order)

    return order


def order_completed(order: Order):
    time.sleep(5)  # 의도적 5초 지연
    order.status = "completed"
    order.save()
    # Redis stream event

    redis.xadd("order_completed", order.dict(), "*")
