# Running Tests Locally

This guide details how to run the GeoNode test suite locally using Docker Compose.

## Prerequisites
- Docker and Docker Compose installed.

## Step 1: Start the Test Environment
Run the following command to build and start the test containers. The `--build` flag ensures you are using the latest code and configuration.

```bash
docker compose -f docker-compose-test.yml up -d --build
```

## Step 2: Wait for Services
Wait for the database and dependent services to be ready. You can check the status with:

```bash
docker compose -f docker-compose-test.yml ps
```

Ensure `db` and `django` services are running. The Django service might report `unhealthy` initially if the healthcheck is strict, but for testing, we use a relaxed healthcheck.

## Step 3: Run Tests
You can run the entire suite or specific modules.

### Run All Tests
```bash
docker compose -f docker-compose-test.yml exec django python manage.py test geonode.people.tests geonode.base.tests --noinput
```
*(Note: Running the full suite takes time. The command above runs the key modules we worked on.)*

### Run Specific Tests
To run a specific test file or class:
```bash
docker compose -f docker-compose-test.yml exec django python manage.py test geonode.people.tests.PeopleTest --noinput
```

## Step 4: Stop the Environment
When finished, stop the containers and remove volumes to clean up:

```bash
docker compose -f docker-compose-test.yml down -v
```

## Common Issues
- **Permission Errors**: If you encounter database permission errors, ensure the `geonode` user has superuser privileges (automatically handled in recent fixes, but can be forced via `docker compose -f docker-compose-test.yml exec db psql -U postgres -c "ALTER USER geonode WITH SUPERUSER;"`).
- **Code Changes**: The local directory is mounted to `/usr/src/geonode` in the container, so local code changes are reflected immediately (except for new dependencies, which require a rebuild).
