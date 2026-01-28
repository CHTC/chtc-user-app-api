FROM python:3.12-alpine

EXPOSE 8000

# Set the working directory
WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY userapp ./userapp
COPY alembic.ini alembic.ini
COPY alembic ./alembic

ENV PYTHON_ENV=production

CMD ["uvicorn", "userapp.main:app", "--host", "0.0.0.0", "--proxy-headers", "--forwarded-allow-ips", "*"]
