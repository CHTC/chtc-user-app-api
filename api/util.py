from fastapi import HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import DeclarativeBase
from starlette.responses import Response
from sqlalchemy import select, func
from sqlalchemy.sql.selectable import Select

from api.query_parser import QueryParser


def with_db_error_handling(func):
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except (DBAPIError, IntegrityError) as e:
            if hasattr(e, 'orig') and e.orig:
                error_message = f"Database error: {e.orig}"
            else:
                error_message = f"Database error: {str(e)}"
            raise HTTPException(status_code=400, detail=error_message)
        except ValidationError as e:
            raise HTTPException(status_code=500, detail=f"Data validation error: {str(e)}")
    return wrapper

@with_db_error_handling
async def list_select_stmt(session, select_stmt: Select, model: type[DeclarativeBase], response_schema: type[BaseModel], response: Response, filter_query_params, page: int = 0, page_size: int = 100) -> list[BaseModel]:
    """Generic list endpoint generator"""

    query_parser = QueryParser(columns=model.__table__.c, query_params=filter_query_params)

    select_stmt = select_stmt \
        .limit(page_size) \
        .offset(page_size * page) \
        .where(query_parser.where_expressions())

    if query_parser.get_order_by_columns() is not None and \
            query_parser.get_group_by_column() is None:
        select_stmt = select_stmt.order_by(*query_parser.get_order_by_columns())

    result = await session.execute(select_stmt)
    groups = result.fetchall()
    num_groups = await session.execute(
        select(func.count()).select_from(select_stmt.subquery())
    )
    response.headers["X-Total-Count"] = str(num_groups.scalar())
    return [response_schema.model_validate(group) for group in groups]


async def list_endpoint(session, model: type[DeclarativeBase], response_schema: type[BaseModel], response: Response, filter_query_params, page: int = 0, page_size: int = 100) -> list[BaseModel]:
    """Generic list endpoint generator"""

    query_parser = QueryParser(columns=model.__table__.c, query_params=filter_query_params)
    return await list_select_stmt(select_stmt=select(*query_parser.get_select_columns()), model=model, response_schema=response_schema, response=response, filter_query_params=filter_query_params, page=page, page_size=page_size, session=session)


@with_db_error_handling
async def get_one_endpoint(session, model: type[DeclarativeBase], response_schema: type[BaseModel], id: str) -> BaseModel:
    """Generic get one endpoint generator"""

    select_stmt = select(model).where(model.id == id)
    result = await session.scalar(select_stmt)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Item not found")
    return response_schema.model_validate(result)

@with_db_error_handling
async def create_one_endpoint(session, model: type[DeclarativeBase], response_schema: type[BaseModel], item: BaseModel) -> BaseModel:
    """Generic create one endpoint generator"""

    db_item = model(**item.model_dump())
    session.add(db_item)
    await session.flush()  # db_item.id is now available
    await session.refresh(db_item)
    return response_schema.model_validate(db_item)

@with_db_error_handling
async def update_one_endpoint(session, model: type[DeclarativeBase], response_schema: type[BaseModel], id: str, item: BaseModel) -> BaseModel:
    """Generic update one endpoint generator"""

    select_stmt = select(model).where(model.id == id)
    db_item = await session.scalar(select_stmt)
    if db_item is None:
        raise HTTPException(status_code=404, detail=f"Item not found")
    for key, value in item.model_dump(exclude_unset=True).items():
        setattr(db_item, key, value)
    await session.flush()
    await session.refresh(db_item)
    return response_schema.model_validate(db_item)

@with_db_error_handling
async def delete_one_endpoint(session, model: type[DeclarativeBase], id: str) -> None:
    """Generic delete one endpoint generator"""

    select_stmt = select(model).where(model.id == id)
    db_item = await session.scalar(select_stmt)
    if db_item is None:
        raise HTTPException(status_code=404, detail=f"Item not found")
    await session.delete(db_item)
    await session.flush()


