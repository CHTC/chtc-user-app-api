from fastapi import HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import DeclarativeBase
from starlette.responses import Response
from sqlalchemy import select, func
from sqlalchemy.sql.selectable import Select
from sqlalchemy.dialects import postgresql
from typing import TypeVar, Union

from userapp.query_parser import QueryParser


def with_db_error_handling(func):
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except (DBAPIError, IntegrityError):
            raise HTTPException(status_code=400, detail="Database error occurred, likely due to violation of constraints.")
        except ValidationError as e:
            raise HTTPException(status_code=500, detail=f"Data validation error: {str(e)}")
    return wrapper

T = TypeVar("T", bound=BaseModel)


@with_db_error_handling
async def list_select_stmt(session, select_stmt: Select, model: type[DeclarativeBase], response: Response, filter_query_params, page: int = 0, page_size: int = 100):
    """Generic list endpoint generator"""

    query_parser = QueryParser(columns=model.__table__.c, query_params=filter_query_params)

    paginated_select_stmt = select_stmt \
        .limit(page_size) \
        .offset(page_size * page) \
        .where(query_parser.where_expressions())

    if query_parser.get_order_by_columns() is not None and \
            query_parser.get_group_by_column() is None:
        paginated_select_stmt = paginated_select_stmt.order_by(*query_parser.get_order_by_columns())

    print(paginated_select_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    result = await session.execute(paginated_select_stmt)
    results = result.unique().fetchall()

    # Get the total count for pagination
    count_stmt = select(func.count()).select_from(select_stmt.where(query_parser.where_expressions()).subquery())

    print(count_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    num_results_total = await session.execute(count_stmt)
    response.headers["X-Total-Count"] = str(num_results_total.scalar())

    # Depending on the select statement, if you use columns you can return directly, if you use models you need to extract from Row
    return [x[0] for x in results]


async def list_endpoint(session, model: type[DeclarativeBase], response: Response, filter_query_params, page: int = 0, page_size: int = 100):
    """Generic list endpoint generator"""
    return await list_select_stmt(select_stmt=select(model), model=model, response=response, filter_query_params=filter_query_params, page=page, page_size=page_size, session=session)


@with_db_error_handling
async def get_one_endpoint(session, model: type[DeclarativeBase], model_id: Union[str, int]):
    """Generic get one endpoint generator"""

    select_stmt = select(model).where(model.id == model_id)
    result = await session.scalar(select_stmt)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Item not found")
    return result

@with_db_error_handling
async def create_one_endpoint(session, model: type[DeclarativeBase], item: T):
    """Generic create one endpoint generator"""

    db_item = model(**item.model_dump())
    session.add(db_item)
    await session.flush()  # db_item.id is now available
    await session.refresh(db_item)
    return db_item

@with_db_error_handling
async def update_one_endpoint(session, model: type[DeclarativeBase], model_id: Union[str, int], item: T):
    """Generic update one endpoint generator"""

    select_stmt = select(model).where(model.id == model_id)
    db_item = await session.scalar(select_stmt)
    if db_item is None:
        raise HTTPException(status_code=404, detail=f"Item not found")
    for key, value in item.model_dump(exclude_unset=True).items():
        setattr(db_item, key, value)
    await session.flush()
    await session.refresh(db_item)
    return db_item

@with_db_error_handling
async def delete_one_endpoint(session, model: type[DeclarativeBase], model_id: Union[str, int]) -> None:
    """Generic delete one endpoint generator"""

    select_stmt = select(model).where(model.id == model_id)
    db_item = await session.scalar(select_stmt)
    if db_item is None:
        raise HTTPException(status_code=404, detail=f"Item not found")
    await session.delete(db_item)
    await session.flush()
