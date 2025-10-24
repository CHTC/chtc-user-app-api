from collections.abc import Callable
from typing import Type

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import DeclarativeBase, Session
from starlette.responses import Response


def create_crud_router(
    session: Callable[Session],
    name: str,
    db_model: Type[DeclarativeBase],
    get_schema: Type[BaseModel],
    create_schema: Type[BaseModel],
    update_schema: Type[BaseModel]
):
    router = APIRouter(
        prefix=f"/{name}",
        responses={
            404: {
                "description": "Not found"
            }
        }
    )

    @router.get("/", response_model=list[get_schema])
    async def read_items(response: Response, skip: int = 0, limit: int = 100):
        async with session() as db_session:
            items = await db_session.query(db_model).offset(skip).limit(limit).all()

            # Add total count header
            total_count = db_session.query(db_model).count()
            response.headers["X-Total-Count"] = str(total_count)

            return items

    @router.post("/", response_model=get_schema)
    async def create_item(item: create_schema):
        async with session() as db_session:
            db_item = await db_model(**item.dict())
            db_session.add(db_item)
            await db_session.commit()
            await db_session.refresh(db_item)
            return db_item

    @router.get("/{item_id}", response_model=get_schema)
    async def read_item(item_id: int):
        async with session() as db_session:
            db_item = await db_session.query(db_model).filter(db_model.id == item_id).first()
            if db_item is None:
                raise HTTPException(status_code=404, detail="Item not found")
            return db_item

    @router.put("/{item_id}", response_model=get_schema)
    async def update_item(item_id: int, item: update_schema):
        async with session() as db_session:
            db_item = await db_session.query(db_model).filter(db_model.id == item_id).first()
            if db_item is None:
                raise HTTPException(status_code=404, detail="Item not found")
            for key, value in item.dict(exclude_unset=True).items():
                setattr(db_item, key, value)
            await db_session.commit()
            await db_session.refresh(db_item)
            return db_item

    @router.delete("/{item_id}")
    async def delete_item(item_id: int):
        async with session() as db_session:
            db_item = await db_session.query(db_model).filter(db_model.id == item_id).first()
            if db_item is None:
                raise HTTPException(status_code=404, detail="Item not found")
            await db_session.delete(db_item)
            await db_session.commit()
            return {"detail": "Item deleted"}

    return router