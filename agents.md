# GeoNode AI Agent Guide

This document provides essential context and guidance for AI coding assistants working on the GeoNode project.

## Project Overview

**GeoNode** is a geospatial content management system built on Django, providing a platform for managing and publishing geospatial data. It integrates mature open-source projects including:

- **Django 4.2** - Web framework
- **GeoServer** - Geospatial server for sharing and editing data
- **PostgreSQL/PostGIS** - Spatial database
- **RabbitMQ** - Message broker for async tasks
- **Celery** - Distributed task queue

## Architecture

### Technology Stack

- **Backend**: Django 4.2.17, Python 3.10
- **Database**: PostgreSQL 15 with PostGIS extension
- **Geospatial**: GeoServer 2.24.4
- **Task Queue**: Celery with RabbitMQ
- **Frontend**: React-based MapStore2 client
- **Deployment**: Docker Compose

### Key Components

1. **Core Apps** (`geonode/`):
   - `base/` - Base models and utilities
   - `layers/` - Layer management
   - `maps/` - Map composition
   - `documents/` - Document handling
   - `geoserver/` - GeoServer integration
   - `upload/` - File upload handling
   - `importer/` - New data import system

2. **Configuration Files**:
   - `settings.py` - Main Django settings (2400+ lines)
   - `.env_test` - Test environment variables
   - `docker-compose.yml` - Production Docker setup
   - `docker-compose-test.yml` - Test Docker setup

## Development Environment

### Docker is Required

**Critical**: All development and testing MUST be done using Docker. The project has complex dependencies that cannot be easily installed locally:

```bash
# Start development environment
docker compose up -d

# Access Django shell
docker compose exec django python manage.py shell

# Run migrations
docker compose exec django python manage.py migrate
```

### DevContainer Support

The project includes VS Code devcontainer configuration (`.devcontainer/`). This is the recommended development setup.

## Testing Infrastructure

### Test Execution

**Important**: Tests require the full Docker stack to be running:

```bash
# Start all test services
docker compose -f docker-compose-test.yml up -d

# Wait for services to be healthy (critical!)
docker compose -f docker-compose-test.yml ps

# Run tests
docker compose -f docker-compose-test.yml exec django ./test.sh
```

### Test Scripts

Multiple test scripts exist for different test suites:

- `test.sh` - Main test suite with coverage
- `test_api_v2.sh` - API v2 tests
- `test_csw.sh` - CSW catalogue tests
- `test_integration.sh` - Integration tests
- `test_oauth2.sh` - OAuth2 tests
- `test_upload.sh` - Upload tests

### Database Permissions

**Critical Issue**: Test databases require superuser privileges to create PostGIS extension.

- `.env_test` uses `DATABASE_URL=postgis://postgres:postgres@db:5432/geonode`
- If you encounter "permission denied to create extension" errors, drop stale test databases:

```bash
docker compose -f docker-compose-test.yml exec -T db sh -c "psql -U postgres -c 'DROP DATABASE IF EXISTS test_geonode;'"
```

### Test Configuration

- `pytest.ini` - pytest configuration (BDD tests in `geonode/tests/bdd/e2e/`)
- `test.sh` uses `--keepdb` flag to reuse test database
- Coverage tracking enabled with `coverage run`

## Common Gotchas

### 1. Environment Variables

- Docker Compose uses `.env` files extensively
- `docker-compose-test.yml` requires `.env_test`
- Missing variables cause silent failures or defaults
- Always check `docker compose config` to verify actual values

### 2. Service Dependencies

- `paver setup_data` requires Django server to be running
- GeoServer must be healthy before importing layers
- RabbitMQ needed for async tasks
- All services must be up for full functionality

### 3. Database Configuration

- `POSTGRESQL_MAX_CONNECTIONS` must have default value: `${POSTGRESQL_MAX_CONNECTIONS:-200}`
- Test database needs superuser for PostGIS extension
- `dj_database_url` parses `DATABASE_URL` environment variable

### 4. Branch Naming

- Main development branch is `main` (not `master`)
- GitHub Actions workflows target `main` and `4.*` branches

## File Locations

### Configuration
- `/geonode/settings.py` - Main Django settings
- `/.env_test` - Test environment variables
- `/docker-compose-test.yml` - Test Docker configuration
- `/pytest.ini` - pytest configuration

### Documentation
- `/TESTING.md` - Comprehensive testing guide
- `/CONTRIBUTING.md` - Contribution guidelines
- `/README.md` - Project overview

### CI/CD
- `/.github/workflows/tests.yml` - Test automation
- `/.github/workflows/flake8.yml` - Code quality checks

### Test Scripts
- `/test.sh` - Main test runner
- `/test_*.sh` - Specialized test suites
- `/pavement.py` - Paver tasks for setup

## Making Changes

### Before Starting

1. **Check existing issues** on GitHub
2. **Create a branch** from `main`: `git checkout -b issue-XX-description`
3. **Start Docker environment**: `docker compose up -d`
4. **Verify services are healthy**: `docker compose ps`

### Development Workflow

1. Make changes in your editor
2. Test locally using Docker: `docker compose exec django python manage.py test`
3. Run full test suite: `docker compose -f docker-compose-test.yml exec django ./test.sh`
4. Check code quality: `flake8` and `black`
5. Commit with descriptive messages
6. Push and create PR to `main`

### Testing Changes

Always test in Docker:

```bash
# Unit tests
docker compose exec django python manage.py test geonode.layers.tests

# Integration tests
docker compose -f docker-compose-test.yml up -d
docker compose -f docker-compose-test.yml exec django ./test_integration.sh

# Specific test
docker compose exec django python manage.py test geonode.layers.tests.test_models.LayerTestCase.test_layer_creation
```

## CI/CD Pipeline

### GitHub Actions

- **tests.yml**: Runs all test scripts on PRs to `main`
  - Uses `continue-on-error: true` to document failures
  - Runs: main tests, API v2, CSW, integration, OAuth2, upload
  - Provides test results summary

- **flake8.yml**: Code quality checks on PRs to `main` and `4.*`

### Expected Behavior

- Tests may have some failures (documented in separate issues)
- CI runs automatically on PR creation
- Check workflow logs for detailed error information

## Debugging Tips

### Container Logs

```bash
# View Django logs
docker compose logs django

# Follow logs in real-time
docker compose logs -f django

# Check specific service
docker compose -f docker-compose-test.yml logs geoserver
```

### Database Access

```bash
# Connect to database
docker compose exec db psql -U postgres -d geonode

# List databases
docker compose exec db psql -U postgres -c "\l"

# Check extensions
docker compose exec db psql -U postgres -d geonode -c "\dx"
```

### Django Shell

```bash
# Access Django shell
docker compose exec django python manage.py shell

# Check settings
docker compose exec django python -c "from django.conf import settings; print(settings.DATABASES)"
```

### Common Fixes

**1. Source Code Sync**
If local changes aren't reflecting in the container, ensure the volume is mounted:
```yaml
volumes:
  - .:/usr/src/geonode
```

**2. Upload Size Limits**
If tests fail with "Total upload size exceeds 1 byte", update the `UploadSizeLimit` in the DB:
```bash
docker compose -f docker-compose-test.yml exec django python -c "from geonode.upload.models import UploadSizeLimit; UploadSizeLimit.objects.update(max_size=104857600)"
```

**3. Missing Dependencies**
If modules are missing (e.g., `importer_datapackage`), check `requirements.txt` and install manually if needed:
```bash
docker compose -f docker-compose-test.yml exec django pip install -r requirements.txt
```


- **Documentation**: https://docs.geonode.org/
- **GitHub**: https://github.com/GeoNode/geonode
- **Demo**: https://development.demo.geonode.org
- **Community**: https://geonode.org/community/

## Recent Changes (Issue #71)

### Test Infrastructure Setup

- Created `TESTING.md` with comprehensive testing guide
- Added `.github/workflows/tests.yml` for CI/CD
- Fixed `POSTGRESQL_MAX_CONNECTIONS` in `docker-compose-test.yml`
- Updated `flake8.yml` to target `main` branch
- Fixed test database permissions by using `postgres` superuser

### Known Issues

- Some tests may fail (being addressed in separate PRs)
- `paver setup_data` requires running Django server
- Test execution can be slow (~80 seconds per layer import)

## Contributing

1. Read `CONTRIBUTING.md`
2. Create issue or pick existing one
3. Create branch: `issue-XX-description`
4. Make changes and test thoroughly
5. Update documentation if needed
6. Submit PR with clear description
7. Reference issue number in PR

## Questions?

- Check `TESTING.md` for testing questions
- Review `CONTRIBUTING.md` for contribution guidelines
- Search existing GitHub issues
- Ask in GeoNode community channels
