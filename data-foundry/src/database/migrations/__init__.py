"""
Database migrations package for Data Foundry.

This package contains migration scripts for database schema changes,
including the AML (Anti-Money Laundering) service MLP schema.

Migrations:
- add_aml_transaction_labels_table: Core AML labels table (001)
- add_aml_audit_trail_tables: Audit trail and compliance tables (002)
"""

# This file intentionally left minimal to avoid circular imports
# Import migration modules directly when needed:
#   from src.database.migrations.add_aml_transaction_labels_table import upgrade, downgrade
#   from src.database.migrations.add_aml_audit_trail_tables import upgrade, downgrade
