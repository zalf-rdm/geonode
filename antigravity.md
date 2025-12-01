# GeoNode Testing Infrastructure

## Key Findings

### Test Execution
- Tests **must** run inside Docker containers with the full stack (PostgreSQL, GeoServer, RabbitMQ, etc.)
- The `test.sh` script runs `paver setup_data` which requires a running Django server to import test data via HTTP
- Cannot run tests locally without Docker due to complex dependencies

### Docker Compose Configuration
- `docker-compose-test.yml` provides the complete test environment
- **Critical fix**: `POSTGRESQL_MAX_CONNECTIONS` variable must have a default value or database fails to start
  - Fixed with: `command: postgres -c "max_connections=${POSTGRESQL_MAX_CONNECTIONS:-200}"`

### Test Scripts
Multiple test scripts exist for different test suites:
- `test.sh` - Main test suite with coverage
- `test_api_v2.sh` - API v2 tests
- `test_csw.sh` - CSW catalogue tests  
- `test_integration.sh` - Integration tests
- `test_oauth2.sh` - OAuth2 tests
- `test_upload.sh` - Upload tests

### GitHub Actions
- Existing `flake8.yml` only checks code formatting
- Branch references updated from `master` to `main`
- New `tests.yml` workflow runs all test scripts on PRs to main

## Implementation Notes

### Documentation (TESTING.md)
- Comprehensive guide for Docker-based testing
- Documents all test scripts and how to run them
- Includes troubleshooting section
- Emphasizes waiting for services to be healthy before running tests

### CI/CD (tests.yml)
- Uses `continue-on-error: true` to document failures without blocking PRs
- Runs all test scripts to get comprehensive coverage
- Provides test results summary in GitHub Actions
- Shows logs on failure for debugging

### Known Issues
Test failures should be documented and addressed in a separate PR as agreed with the user.

## Future Work
- Monitor test results in CI to identify failing tests
- Create separate issues/PRs to fix identified test failures
- Consider adding test coverage reporting
- May need to optimize test execution time if it becomes too long
