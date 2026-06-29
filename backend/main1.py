from fastapi import FastAPI, HTTPException, status, Query
from pydantic import BaseModel, EmailStr, Field
from typing import Annotated



# 创建 FastAPI 应用实例，后续通过装饰器注册接口
app = FastAPI()



@app.get("/")
def read_root():
    # 项目的根路径，用于快速确认服务是否正常运行
    return {"Hello": "World"}

# task_id 是路径参数，FastAPI 会自动将它校验并转换为整数
# @app.get("/tasks/{task_id}")
# def read_task(task_id: int):
#     return {"task_id": task_id,
#             'title': '学习fastAPI',
#             'description': '学习fastAPI的基本使用',
#             'completed': False
#             }   

@app.get("/users/{user_id}")
def read_user(user_id: int):
    return {"user_id": user_id,
            'name': '张三',
            'email': 'zhangsan@example.com',
            'is_active': True
            }

# completed 和 limit 是可选的查询参数，例如：/tasks/?completed=true&limit=5
# @app.get("/tasks/")
# def list_tasks(completed: bool | None = None, limit: int = 10):
#     return {"completed": completed,
#             'limit': limit,
#             }

# 定义创建、更新任务时请求体的数据结构
# class TaskCreate(BaseModel):
#     title: str
#     # 可选字段，不传时默认为 None
#     description: str | None = None
#     completed: bool = False

# @app.post("/tasks/")
# def create_task(task: TaskCreate):
#     # task 来自 JSON 请求体，并由 Pydantic 自动完成类型校验
#     return {"message": "任务创建成功",
#             'title': task.title,
#             'description': task.description,
#             'completed': task.completed
#             }

# @app.put("/tasks/{task_id}")
# def update_task(task_id: int,task: TaskCreate, notify: bool = False):
#     # task_id 来自路径，task 来自请求体，notify 来自查询参数
#     return {"message": "任务更新成功",
#             'task_id': task_id,
#             'title': task.title,
#             'description': task.description,
#             'completed': task.completed
#             }

# 商品请求体模型，并通过 Field 为字段添加校验规则
class Product(BaseModel):
    # 商品名称长度必须在 2～50 个字符之间
    name: str = Field(min_length=2, max_length=50)
    # 商品价格必须大于 0
    price: float = Field(gt=0)
    # 商品描述可以不传，最多 200 个字符
    description: str | None = Field(default=None, max_length=200)
    in_stock: bool = True

@app.post("/products")
def create_product(product: Product, discount: Annotated[float, Query(gt=0, le=1)] = 1.0):
    # discount 是查询参数，取值范围为 (0, 1]，默认不打折
    return {"message": "产品创建成功",
            'name': product.name,
            'price': product.price,
            'description': product.description,
            'in_stock': product.in_stock,
            'discount_price': product.price * discount
            }


# 用户请求体模型
class User(BaseModel):
    # 用户名长度必须在 3～20 个字符之间
    username: str = Field(min_length=3, max_length=20)
    # 用户年龄必须大于 18 且不超过 120
    age: int = Field(gt=18, le=120)
    # EmailStr 会检查邮箱格式，需要安装 email-validator
    email: EmailStr
    bio: str | None = Field(default=None, max_length=100)

@app.post("/users")
def create_user(user: User, send_email: bool = True):
    # send_email 是查询参数，默认值为 True
    return {"message": "用户创建成功",
            'username': user.username,
            'age': user.age,
            'email': user.email,
            'bio': user.bio,
            'send_email': send_email,
            }


# 第四节 内存版CRUD示例

# 定义请求和响应模型
class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str | None = None
    completed: bool = False

class TaskResponse(TaskCreate):
    id: int

# 模拟数据库
tasks: dict[int, TaskResponse] = {}
next_id = 1

# {
#     1: TaskResponse(...),
#     2: TaskResponse(...)
# }

# 创建任务
@app.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(task: TaskCreate):
    global next_id
    new_task = TaskResponse(id=next_id, **task.model_dump())
    tasks[next_id] = new_task
    next_id += 1
    return new_task

# # 查询全部任务
# @app.get("/tasks", response_model=list[TaskResponse])
# def list_tasks(completed: bool | None = None):
#     if completed == True:
#         filtered_tasks = [task for task in tasks.values() if task.completed == completed]
#         return filtered_tasks
#     elif completed == False:
#         filtered_tasks = [task for task in tasks.values() if task.completed == completed]
#         return filtered_tasks
#     return list(tasks.values())


# 查询全部任务并分页
@app.get("/tasks", response_model=list[TaskResponse])
def list_tasks(completed: bool | None = None, skip: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=100)] = 10):
    all_tasks = list(tasks.values())
    if completed is not None:
        all_tasks = [task for task in all_tasks if task.completed == completed]
    return all_tasks[skip: skip + limit]




# 查询单个任务
@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: int):
    task = tasks.get(task_id)

    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    return task

# 第四节下，更新和删除任务的接口
# 更新

@app.put("/tasks/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, task: TaskCreate):
    if task_id not in tasks:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    updated_task = TaskResponse(id=task_id, **task.model_dump())
    tasks[task_id] = updated_task
    return updated_task

# 删除任务
@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int):
    if task_id not in tasks:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    del tasks[task_id]
    return None

# 部分更新
# class TaskUpdate(BaseModel):
#     title: str | None = Field(default=None, min_length=1, max_length=100)
#     description: str | None = Field(default=None)

# @app.patch("/tasks/{task_id}", response_model=TaskResponse)
# def partial_update_task(task_id: int, task: TaskUpdate):
#     if task_id not in tasks:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    
#     existing_task = tasks[task_id]
#     updated_data = task.model_dump(exclude_unset=True)
#     updated_task = existing_task.model_copy(update=updated_data)
#     tasks[task_id] = updated_task
#     return updated_task


# class UserCreate(BaseModel):
#     username: str = Field(min_length=3, max_length=20)
#     email: EmailStr
#     password: str = Field(min_length=6)

# class UserResponse(BaseModel):
#     id: int
#     username: str
#     email: EmailStr

# @app.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
# def create_user(user: UserCreate):
#     return UserResponse(id=1, username=user.username, email=user.email, password=user.password)

# @app.get("/users", response_model=list[UserResponse])
# def list_users():
#     return [
#         {"id": 1, "username": "john_doe1", "email": "john@example.com", "password": "hashed_password1"},
#         {"id": 2, "username": "jane_doe2", "email": "jane@example.com", "password": "hashed_password2"}
#     ]

# 商品练习
# class ProductCreate1(BaseModel):
#     name: str = Field(min_length=2, max_length=50)
#     price: float = Field(gt=0)
#     cost_price: float = Field(gt=0)
#     description: str | None = Field(default=None, max_length=200)

# class ProductResponse1(BaseModel):
#     id: int
#     name: str
#     price: float
#     description: str | None = None

# class ProductInternal(ProductResponse1):
#     cost_price: float

# @app.post("/products1", response_model=ProductResponse1, status_code=status.HTTP_201_CREATED)
# def create_product(product: ProductCreate1):
#     return ProductInternal(id=1, name=product.name, price=product.price, cost_price=product.cost_price, description=product.description)