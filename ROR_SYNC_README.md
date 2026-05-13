# ROR Organizations Synchronization

## Overview

This update adds a Django management command to synchronize Research Organization Registry (ROR) organizations with GeoNode's database.

## Background

GeoNode resources can reference organizations through funding information. Organizations must exist in GeoNode before a resource can be published. Previously, organizations were created reactively when users registered or updated their profiles.

This update provides a proactive way to sync organizations from the ROR API.

## Usage

### Fetch and sync a specific ROR:
```bash
python manage.py update_ror_organizations --ror-ids 04m219c69
```

### Fetch and sync multiple RORs:
```bash
python manage.py update_ror_organizations --ror-ids 04m219c69 02kzdsw93 015w4jd94
```

### Fetch and sync all ROR organizations (large dataset):
```bash
python manage.py update_ror_organizations --all
```

## Command Details

**File:** `geonode/base/management/commands/update_ror_organizations.py`

**Features:**
- Fetches organization data from the ROR API (https://api.ror.org)
- Creates new organizations if they don't exist
- Updates existing organizations if name or abbreviation changed
- Handles pagination for large result sets
- Provides detailed console output with summary statistics
- Transactions ensure data consistency

**Output:**
- ✓ Created: New organizations added to database
- ✓ Updated: Existing organizations with changes applied
- ✓ Unchanged: Organizations already in sync
- ✗ Error: Any issues encountered during processing

**Summary Statistics:**
- Count of created, updated, and failed organizations
- Total organizations processed

## Example: Fixing Upload Failures

If you encounter an error like:
```
Missing organizations in GeoNode for funding ROR(s): https://ror.org/04m219c69
```

Run the following to populate the missing ROR:
```bash
python manage.py update_ror_organizations --ror-ids 04m219c69
```

Then retry the publication workflow in upload-tool.

## Configuration

Optional Django settings (in `settings.py`):
```python
# ROR API base URL (defaults to https://api.ror.org)
ROR_API_BASE_URL = "https://api.ror.org"
```

## Notes

- The command uses `requests` library (already a dependency in GeoNode)
- All database operations are wrapped in a transaction for consistency
- ROR IDs can be provided with or without the `https://ror.org/` prefix
- The command handles pagination automatically for `--all` operations
