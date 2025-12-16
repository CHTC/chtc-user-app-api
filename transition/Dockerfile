# Use an official Python image
FROM python:3.12-slim

# Install PostgreSQL client
RUN apt-get update && apt-get install -y postgresql-client && rm -rf /var/lib/apt/lists/*

# Set workdir
WORKDIR /app

# Copy requirements and install dependencies
COPY ../requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY userapp ./userapp
COPY transition/full_migration.sh full_migration.sh
COPY transition/pre-script.sql pre-script.sql
COPY transition/post-script.sql post-script.sql
COPY transition/migrate.py migrate.py
COPY transition/intermediate_models.py intermediate_models.py

# Make the migration script executable
RUN chmod +x full_migration.sh

# Set environment variables (override with docker run -e ...)
ENV PYTHONUNBUFFERED=1

# Entrypoint
ENTRYPOINT ["/bin/bash", "./full_migration.sh"]

