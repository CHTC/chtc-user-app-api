Generic single-database configuration with an async dbapi.

# Updating the Database Schema

To update the database schema do the following steps:

1. Install Alembic if you don't have it already:

   ```bash
   pip install alembic
   ```
   
2. Update your models in `/core/models/*` as needed.

3. Generate a new migration script:

   ```bash
   alembic revision --autogenerate -m "Your migration message here"
   ```
   
4. Review the generated migration script in the `alembic/versions/` directory to ensure it accurately reflects the changes you want to make.

5. Apply the migration to the dev database.

   ```bash
   alembic upgrade head
   ```
   
6. Test your application to ensure everything works as expected with the new schema.

## Notes

You should only have on version per PR. If you need to modify a migration during testing revert back the previous migration first before generating a new one.

# Update Image

```bash
docker build --file ./alembic/Dockerfile --platform linux/amd64 -t hub.opensciencegrid.org/opensciencegrid/chtc-userapp-alembic:1.0.0 .
```

```bash
docker run --env-file .env --network host hub.opensciencegrid.org/opensciencegrid/chtc-userapp-alembic:1.0.0
```
