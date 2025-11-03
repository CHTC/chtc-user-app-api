FROM python:3.12-alpine

EXPOSE 8000

# Set the working directory
WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY api ./api

WORKDIR /app/api

CMD ["python", "app.py"]
