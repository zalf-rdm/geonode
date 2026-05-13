"""
Management command to synchronize ROR (Research Organization Registry) organizations
from the ROR API into the GeoNode database.

Usage:
    python manage.py update_ror_organizations [--all] [--ror-ids ROR_ID1 ROR_ID2]
    
Options:
    --all: Fetch and update all organizations from ROR API (requires pagination handling)
    --ror-ids: Fetch and update specific ROR IDs (space-separated)
"""

import requests
import logging
from typing import Optional, Dict, List, Tuple

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.conf import settings

from geonode.base.models import Organization

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Synchronize ROR organizations with GeoNode database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="Fetch and update all organizations from ROR API",
        )
        parser.add_argument(
            "--ror-ids",
            nargs="+",
            help="Fetch and update specific ROR IDs (e.g., 04m219c69 02kzdsw93)",
        )

    def fetch_from_ror_api(self, ror_ids: Optional[List[str]] = None) -> List[Dict]:
        """
        Fetch organization data from ROR API.
        
        Args:
            ror_ids: List of ROR IDs to fetch. If None, fetch all (paginated).
            
        Returns:
            List of organization dicts with id, name, acronyms, country.
        """
        organizations = []
        ror_api_base = getattr(settings, "ROR_API_BASE_URL", "https://api.ror.org")

        if ror_ids:
            # Fetch specific RORs
            for ror_id in ror_ids:
                # Remove protocol if present
                ror_id = ror_id.replace("https://ror.org/", "").replace("http://ror.org/", "")
                try:
                    url = f"{ror_api_base}/organizations/{ror_id}"
                    response = requests.get(url, timeout=10)
                    response.raise_for_status()
                    org_data = response.json()
                    organizations.append(org_data)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✓ Fetched ROR {ror_id}: {org_data.get('name')}"
                        )
                    )
                except requests.exceptions.RequestException as e:
                    self.stdout.write(
                        self.style.ERROR(f"✗ Failed to fetch ROR {ror_id}: {e}")
                    )
        else:
            # Fetch all (paginated)
            page = 1
            per_page = 100
            while True:
                try:
                    url = f"{ror_api_base}/organizations"
                    params = {"page": page, "per_page": per_page}
                    response = requests.get(url, params=params, timeout=10)
                    response.raise_for_status()
                    data = response.json()
                    
                    items = data.get("items", [])
                    if not items:
                        break

                    organizations.extend(items)
                    page += 1

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✓ Fetched page {page - 1} ({len(items)} orgs)"
                        )
                    )

                    # Stop if we've fetched all
                    if len(items) < per_page:
                        break
                except requests.exceptions.RequestException as e:
                    self.stdout.write(self.style.ERROR(f"✗ Failed to fetch page {page}: {e}"))
                    break

        return organizations

    def parse_ror_org(self, ror_org: Dict) -> Tuple[str, str, Optional[str]]:
        """
        Parse ROR API response into (ror_id, name, abbreviation).
        
        Args:
            ror_org: Organization data from ROR API
            
        Returns:
            Tuple of (ror_id, name, abbreviation)
        """
        ror_id = ror_org.get("id", "").replace("https://ror.org/", "")
        name = ror_org.get("name", "Unknown")
        
        # Try to get abbreviation from acronyms
        acronyms = ror_org.get("acronyms", [])
        abbreviation = acronyms[0] if acronyms else None
        
        return ror_id, name, abbreviation

    @transaction.atomic
    def handle(self, *args, **options):
        """Main command handler."""
        all_orgs = options.get("all", False)
        ror_ids = options.get("ror_ids", None)

        if not all_orgs and not ror_ids:
            raise CommandError(
                "Provide either --all or --ror-ids ROR_ID1 ROR_ID2 ..."
            )

        self.stdout.write(
            self.style.SUCCESS("\n=== ROR Organization Synchronization ===\n")
        )

        # Fetch from ROR API
        self.stdout.write("Fetching organizations from ROR API...")
        ror_orgs = self.fetch_from_ror_api(ror_ids)

        if not ror_orgs:
            self.stdout.write(self.style.WARNING("No organizations to process."))
            return

        self.stdout.write(
            self.style.SUCCESS(f"\nProcessing {len(ror_orgs)} organizations...\n")
        )

        created_count = 0
        updated_count = 0
        error_count = 0

        for ror_org in ror_orgs:
            try:
                ror_id, name, abbreviation = self.parse_ror_org(ror_org)

                if not ror_id:
                    self.stdout.write(
                        self.style.WARNING(f"⚠ Skipped org with no ROR ID: {name}")
                    )
                    continue

                # Check if organization exists
                org, created = Organization.objects.get_or_create(
                    ror=ror_id,
                    defaults={
                        "organization": name,
                        "abbreviation": abbreviation or "",
                    },
                )

                if created:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✓ Created: {name} (ROR: {ror_id}, Abbr: {abbreviation})"
                        )
                    )
                    created_count += 1
                else:
                    # Update if name or abbreviation changed
                    updated = False
                    if org.organization != name:
                        org.organization = name
                        updated = True
                    if org.abbreviation != (abbreviation or ""):
                        org.abbreviation = abbreviation or ""
                        updated = True

                    if updated:
                        org.save()
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"✓ Updated: {name} (ROR: {ror_id})"
                            )
                        )
                        updated_count += 1
                    else:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"✓ Unchanged: {name} (ROR: {ror_id})"
                            )
                        )

            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"✗ Error processing {ror_org.get('name', 'Unknown')}: {e}"
                    )
                )
                logger.exception("Error processing ROR organization", extra={"ror_org": ror_org})

        # Summary
        self.stdout.write(
            self.style.SUCCESS(
                f"\n=== Summary ===\n"
                f"Created: {created_count}\n"
                f"Updated: {updated_count}\n"
                f"Errors: {error_count}\n"
                f"Total processed: {len(ror_orgs)}\n"
            )
        )
