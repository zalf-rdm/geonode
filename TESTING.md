# Testing GeoNode

This document describes how to run tests for the GeoNode project.

## Requirements

- **Docker** and **Docker Compose** installed on your system
- Access to the GeoNode repository

## Running Tests Locally

### Using Docker (Recommended)

The recommended way to run tests is using Docker Compose, which provides a complete test environment including PostgreSQL, GeoServer, RabbitMQ, and all other required services.

#### 1. Start the Test Environment

```bash
docker compose -f docker-compose-test.yml up -d
```

This will start all required services in the background. **Important:** Wait for all services to be healthy before running tests. You can check the status with:

```bash
docker compose -f docker-compose-test.yml ps
```

Wait until all services show as "healthy" or "running".

#### 2. Run Tests

**Run all tests:**
```bash
docker compose -f docker-compose-test.yml exec django python manage.py test --keepdb
```

**Run specific test scripts:**
```bash
# Main test suite with coverage
docker compose -f docker-compose-test.yml exec django ./test.sh

# API v2 tests
docker compose -f docker-compose-test.yml exec django ./test_api_v2.sh

# CSW catalogue tests
docker compose -f docker-compose-test.yml exec django ./test_csw.sh

# Integration tests
docker compose -f docker-compose-test.yml exec django ./test_integration.sh

# OAuth2 tests
docker compose -f docker-compose-test.yml exec django ./test_oauth2.sh

# Upload tests
docker compose -f docker-compose-test.yml exec django ./test_upload.sh
```

#### 3. Stop the Test Environment

```bash
docker compose -f docker-compose-test.yml down
```

To also remove volumes (clean database):
```bash
docker compose -f docker-compose-test.yml down -v
```

### Using Makefile

Alternatively, you can use the Makefile targets:

```bash
# Run smoke tests
make smoketest

# Run unit tests
make unittest

# Run all tests (smoke + unit)
make test
```

These commands will automatically start the required Docker containers.

## Running Tests in CI/CD

Tests are automatically run on every Pull Request to the `main` branch via GitHub Actions. The workflow:

1. Starts the test environment using `docker-compose-test.yml`
2. Runs all test scripts
3. Reports results and coverage

See [`.github/workflows/tests.yml`](.github/workflows/tests.yml) for the complete workflow configuration.

## Test Configuration

- **Test environment variables:** [`.env_test`](.env_test)
- **Development environment variables:** [`.env_dev`](.env_dev)
- **pytest configuration:** [`pytest.ini`](pytest.ini)
- **Docker test setup:** [`docker-compose-test.yml`](docker-compose-test.yml)

### Cleaning Stale Test Databases

If you encounter `permission denied to create extension "postgis"` errors, you may have stale test databases from previous runs with different user permissions. To fix this:

```bash
# Drop test databases
docker compose -f docker-compose-test.yml exec -T db sh -c "psql -U postgres -c 'DROP DATABASE IF EXISTS test_geonode;' && psql -U postgres -c 'DROP DATABASE IF EXISTS test_geonode_data;'"

# Restart Django container
docker compose -f docker-compose-test.yml restart django

# Run tests again
docker compose -f docker-compose-test.yml exec django ./test.sh
```

## Known Issues

### Integration Test Script
The `test_integration.sh` script uses `paver run_tests` which has different test discovery than the standard `manage.py test`. This is expected behavior and not a configuration error.

### Test Failures
Some tests may fail due to:
- Missing test data
- Service timing issues
- Environment-specific configurations

These failures are being tracked in separate issues and will be addressed in future PRs.

## Troubleshooting

### Database Connection Issues

If you encounter database connection errors:

1. Ensure the database container is healthy:
   ```bash
   docker compose -f docker-compose-test.yml ps
   ```

2. Check database logs:
   ```bash
   docker compose -f docker-compose-test.yml logs db
   ```

3. Restart the database:
   ```bash
   docker compose -f docker-compose-test.yml restart db
   ```

### Port Conflicts

If you get port binding errors, ensure no other services are using the required ports:
- 8000 (Django)
- 8080 (GeoServer)
- 5432 (PostgreSQL)

You can check with:
```bash
sudo netstat -tulpn | grep -E ':(8000|8080|5432)'
```

### Cleaning Up

To completely reset the test environment:

```bash
# Stop and remove all containers, networks, and volumes
docker compose -f docker-compose-test.yml down -v

# Remove any dangling images
docker system prune -f

# Start fresh
docker compose -f docker-compose-test.yml up -d
```

## Development Testing

For development, you can use the development environment:

```bash
# Use the development test script
./test_dev.sh

# Or run specific tests
python manage.py test geonode.layers.tests --keepdb
```

Note: This requires a properly configured development environment with all dependencies installed.

## Writing Tests

When contributing new features, please include tests:

1. **Unit tests:** Test individual components in isolation
2. **Integration tests:** Test component interactions
3. **API tests:** Test REST API endpoints
4. **BDD tests:** Test user workflows (see `geonode/tests/bdd/`)

Follow Django's testing best practices and ensure all tests pass before submitting a PR.
