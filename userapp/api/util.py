from html import escape
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
from functools import lru_cache
import smtplib
import traceback
import logging
from typing import Any, Callable, TypeVar, Union

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import DeclarativeBase
from starlette.responses import Response
from sqlalchemy import select, func
from sqlalchemy.sql.selectable import Select
from sqlalchemy.dialects import postgresql

from userapp.query_parser import QueryParser

SMTP_SERVER = "smtp.wiscmail.wisc.edu"
logger = logging.getLogger(__name__)

def with_db_error_handling(func):
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except (DBAPIError, IntegrityError) as e:
            logger.error(f"Database error: {str(e)}")
            raise HTTPException(status_code=400, detail="Database error occurred, likely due to violation of constraints.")
        except ValidationError as e:
            raise HTTPException(status_code=500, detail=f"Data validation error: {str(e)}")
        except HTTPException:
            # re-throw HTTPExceptions so they can be handled by FastAPI
            raise
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

    return wrapper

T = TypeVar("T", bound=BaseModel)


@with_db_error_handling
async def list_select_stmt(
    session,
    select_stmt: Select,
    model: type[DeclarativeBase],
    response: Response,
    filter_query_params,
    page: int = 0,
    page_size: int = 100,
    load_options=None,
):
    """Generic list endpoint generator"""

    query_parser = QueryParser(columns=model.__table__.c, query_params=filter_query_params)

    paginated_select_stmt = select_stmt \
        .limit(page_size) \
        .offset(page_size * page) \
        .where(query_parser.where_expressions())

    if load_options:
        paginated_select_stmt = paginated_select_stmt.options(*load_options)

    if query_parser.get_order_by_columns() is not None and \
            query_parser.get_group_by_column() is None:
        paginated_select_stmt = paginated_select_stmt.order_by(*query_parser.get_order_by_columns())

    result = await session.execute(paginated_select_stmt)
    results = result.unique().fetchall()

    # Get the total count for pagination
    count_stmt = select(func.count()).select_from(select_stmt.where(query_parser.where_expressions()).subquery())

    num_results_total = await session.execute(count_stmt)
    response.headers["X-Total-Count"] = str(num_results_total.scalar())

    # Depending on the select statement, if you use columns you can return directly, if you use models you need to extract from Row
    return [x[0] for x in results]


async def list_endpoint(
    session,
    model: type[DeclarativeBase],
    response: Response,
    filter_query_params,
    page: int = 0,
    page_size: int = 100,
    load_options=None
):
    """Generic list endpoint generator"""
    return await list_select_stmt(
        select_stmt=select(model),
        model=model,
        response=response,
        filter_query_params=filter_query_params,
        page=page,
        page_size=page_size,
        session=session,
        load_options=load_options,
    )


@with_db_error_handling
async def get_one_endpoint(session, model: type[DeclarativeBase], model_id: Union[str, int], load_options=None):
    """Generic get one endpoint generator"""

    select_stmt = select(model).where(model.id == model_id)
    if load_options:
        select_stmt = select_stmt.options(*load_options)
    result = await session.scalar(select_stmt)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Item not found")
    return result

@with_db_error_handling
async def create_one_endpoint(session, model: type[DeclarativeBase], item: T, load_options=None):
    """Generic create one endpoint generator"""

    db_item = model(**item.model_dump())
    session.add(db_item)
    await session.flush()  # db_item.id is now available
    await session.refresh(db_item)

    if load_options:
        select_stmt = select(model).where(model.id == db_item.id).options(*load_options)
        db_item = await session.scalar(select_stmt)

    return db_item

@with_db_error_handling
async def update_one_endpoint(session, model: type[DeclarativeBase], model_id: Union[str, int], item: T, load_options=None):
    """Generic update one endpoint generator"""

    select_stmt = select(model).where(model.id == model_id)
    db_item = await session.scalar(select_stmt)
    if db_item is None:
        raise HTTPException(status_code=404, detail=f"Item not found")
    for key, value in item.model_dump(exclude_unset=True).items():
        setattr(db_item, key, value)
    await session.flush()
    await session.refresh(db_item)

    if load_options:
        select_stmt = select(model).where(model.id == model_id).options(*load_options)
        db_item = await session.scalar(select_stmt)

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

def route_method_lookup(routes, route, method):
    for r in routes:
        if r.path == route and method in r.methods:
            return True

    return False

def format_escaped_template(template: str, **kwargs) -> str:
    escaped_kwargs = {
        key: escape(str(value), quote=False)
        for key, value in kwargs.items()
    }
    return template.format(**escaped_kwargs)

def send_email(send_from: str, send_to: Union[str, list], cc: Union[str, list], subject: str, text: str, server=SMTP_SERVER):

    # Don't send emails outside of production
    if os.getenv("PYTHON_ENV") != "production":
        print(send_from, send_to, cc, subject, text)
        return


    msg = MIMEMultipart()
    msg['From'] = send_from
    msg['To'] = send_to if isinstance(send_to, str) else ', '.join(send_to)  # Handle the two types
    msg["Cc"] = cc if isinstance(cc, str) else ', '.join(cc)  # Handle the two types
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = subject

    msg.attach(MIMEText(text))

    smtp = smtplib.SMTP(server)
    smtp.sendmail(send_from, send_to, msg.as_string())
    smtp.close()
