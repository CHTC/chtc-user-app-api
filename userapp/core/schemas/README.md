# Pydantic Schemas

This directory has the pydantic models which operate as middlemen between the database models and the API endpoints.

## Structure

Each file in this directory corresponds to a specific database model and contains the following.

### TableSchema

This schema represents the complete structure of the database table, including all fields. 

Typical use case is casting to this schema before creating/patching a db row.

### GET/POST/PATCH Schemas 

These schemas are tailored for specific API operations. 

They include only the fields relevant to the operation, ensuring that clients send and receive only the necessary data.

In the case of POST and PATCH operations you will often cast to a TableSchema before performing the database operation.

### POST/PATCH Full Schemas

These schemas are variants of the POST and PATCH schemas that include all fields you can operate over in a specific operation.

They are useful when you have an endpoint that can operate over many tables.
