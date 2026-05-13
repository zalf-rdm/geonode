#!/bin/bash
# Script to populate ROR organizations in GeoNode

# Example RORs that might be missing (based on the upload-tool submission 159 error)
# Missing ROR: https://ror.org/04m219c69

# Usage:
# 1. SSH into GeoNode container or run locally if Django is configured
# 2. Execute: python manage.py update_ror_organizations --ror-ids 04m219c69

# To fetch a specific ROR:
# python manage.py update_ror_organizations --ror-ids 04m219c69

# To fetch multiple RORs at once:
# python manage.py update_ror_organizations --ror-ids 04m219c69 02kzdsw93 015w4jd94

# To sync all organizations from ROR API (large dataset, may take time):
# python manage.py update_ror_organizations --all

echo "To populate missing RORs in GeoNode, run one of the following:"
echo ""
echo "1. For specific ROR (04m219c69):"
echo "   python manage.py update_ror_organizations --ror-ids 04m219c69"
echo ""
echo "2. For multiple RORs:"
echo "   python manage.py update_ror_organizations --ror-ids 04m219c69 02kzdsw93"
echo ""
echo "3. For all RORs (large dataset):"
echo "   python manage.py update_ror_organizations --all"
