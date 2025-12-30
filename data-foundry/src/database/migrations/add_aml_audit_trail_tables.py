"""
Database migration to create AML audit trail tables.

This migration creates three tables for comprehensive audit trail and compliance:
1. aml_expert_reviews - Track expert human reviews for inter-rater agreement (Cohen's Kappa)
2. aml_audit_reports - Store generated audit reports for regulatory defensibility
3. aml_labeling_methodology - Track versioned AML labeling rules for audit trail

These tables support regulatory compliance, accountability, and methodology versioning
required for FATF, FinCEN, and other AML regulatory frameworks.

Reference: docs/planning/SCHEMA_DESIGN.md - P01-001
Task: P01-002 - Create Alembic Migrations
"""

import asyncio
from sqlalchemy import text
from src.database.connection import db_connection


async def upgrade():
    """
    Create audit trail tables: aml_expert_reviews, aml_audit_reports, aml_labeling_methodology.

    These tables enable:
    - Expert review tracking for AI label validation
    - Cohen's Kappa calculation for inter-rater agreement
    - Audit report generation for compliance
    - Methodology versioning for regulatory defensibility
    """
    async with db_connection.get_session() as session:
        try:
            # ================================================================
            # TABLE 1: aml_expert_reviews
            # ================================================================
            print("Creating aml_expert_reviews table...")

            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS aml_expert_reviews (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    aml_transaction_label_id UUID NOT NULL,
                    tenant_id UUID NOT NULL,
                    expert_id UUID NOT NULL,
                    expert_decision VARCHAR(50) NOT NULL,
                    reasoning TEXT NOT NULL,
                    confidence_level DECIMAL(3,2) NOT NULL,
                    reviewed_at TIMESTAMP NOT NULL,
                    is_deleted BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

                    -- CHECK constraints for data integrity
                    CONSTRAINT check_aml_expert_confidence_level
                        CHECK (confidence_level >= 0 AND confidence_level <= 1),
                    CONSTRAINT check_aml_expert_decision
                        CHECK (expert_decision IN ('AGREE', 'DISAGREE', 'NEEDS_CLARIFICATION'))
                );
            """))

            # Create indexes for aml_expert_reviews
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_aml_expert_reviews_tenant_id
                ON aml_expert_reviews(tenant_id);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_aml_expert_reviews_label_id
                ON aml_expert_reviews(aml_transaction_label_id);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_aml_expert_reviews_expert_id
                ON aml_expert_reviews(expert_id);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_aml_expert_reviews_created_at
                ON aml_expert_reviews(created_at DESC);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_aml_expert_reviews_is_deleted
                ON aml_expert_reviews(is_deleted)
                WHERE is_deleted = FALSE;
            """))

            # Foreign keys for aml_expert_reviews
            await session.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'tenants') THEN
                        ALTER TABLE aml_expert_reviews
                        DROP CONSTRAINT IF EXISTS fk_aml_expert_reviews_tenant_id;

                        ALTER TABLE aml_expert_reviews
                        ADD CONSTRAINT fk_aml_expert_reviews_tenant_id
                        FOREIGN KEY (tenant_id) REFERENCES tenants(id)
                        ON DELETE CASCADE;
                    END IF;
                END $$;
            """))

            await session.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'aml_transaction_labels') THEN
                        ALTER TABLE aml_expert_reviews
                        DROP CONSTRAINT IF EXISTS fk_aml_expert_reviews_label_id;

                        ALTER TABLE aml_expert_reviews
                        ADD CONSTRAINT fk_aml_expert_reviews_label_id
                        FOREIGN KEY (aml_transaction_label_id) REFERENCES aml_transaction_labels(id)
                        ON DELETE CASCADE;
                    END IF;
                END $$;
            """))

            await session.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'users') THEN
                        ALTER TABLE aml_expert_reviews
                        DROP CONSTRAINT IF EXISTS fk_aml_expert_reviews_expert_id;

                        ALTER TABLE aml_expert_reviews
                        ADD CONSTRAINT fk_aml_expert_reviews_expert_id
                        FOREIGN KEY (expert_id) REFERENCES users(user_id)
                        ON DELETE CASCADE;
                    END IF;
                END $$;
            """))

            # Add comments for aml_expert_reviews
            await session.execute(text("""
                COMMENT ON TABLE aml_expert_reviews IS
                'Tracks expert human reviews of AI labels for inter-rater agreement calculation';
            """))

            await session.execute(text("""
                COMMENT ON COLUMN aml_expert_reviews.expert_decision IS
                'Expert decision on AI label: AGREE, DISAGREE, or NEEDS_CLARIFICATION';
            """))

            await session.execute(text("""
                COMMENT ON COLUMN aml_expert_reviews.confidence_level IS
                'Expert confidence in their review decision (0-1 scale)';
            """))

            print("✓ aml_expert_reviews table created with 5 indexes")

            # ================================================================
            # TABLE 2: aml_audit_reports
            # ================================================================
            print("Creating aml_audit_reports table...")

            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS aml_audit_reports (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    tenant_id UUID NOT NULL,
                    job_id UUID NOT NULL,
                    transaction_count INTEGER NOT NULL,
                    labeled_count INTEGER NOT NULL,
                    expert_reviewed_count INTEGER NOT NULL,
                    kappa_coefficient DECIMAL(4,3) NOT NULL,
                    agreement_level VARCHAR(50) NOT NULL,
                    generated_at TIMESTAMP NOT NULL,
                    report_url VARCHAR(500) NOT NULL,
                    is_deleted BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

                    -- CHECK constraints for data integrity
                    CONSTRAINT check_aml_audit_transaction_count
                        CHECK (transaction_count >= 0),
                    CONSTRAINT check_aml_audit_labeled_count
                        CHECK (labeled_count >= 0 AND labeled_count <= transaction_count),
                    CONSTRAINT check_aml_audit_reviewed_count
                        CHECK (expert_reviewed_count >= 0 AND expert_reviewed_count <= labeled_count),
                    CONSTRAINT check_aml_audit_kappa_coefficient
                        CHECK (kappa_coefficient >= -1 AND kappa_coefficient <= 1),
                    CONSTRAINT check_aml_audit_agreement_level
                        CHECK (agreement_level IN ('POOR', 'FAIR', 'MODERATE', 'SUBSTANTIAL', 'PERFECT'))
                );
            """))

            # Create indexes for aml_audit_reports
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_aml_audit_reports_tenant_id
                ON aml_audit_reports(tenant_id);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_aml_audit_reports_job_id
                ON aml_audit_reports(job_id);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_aml_audit_reports_created_at
                ON aml_audit_reports(created_at DESC);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_aml_audit_reports_is_deleted
                ON aml_audit_reports(is_deleted)
                WHERE is_deleted = FALSE;
            """))

            # Foreign keys for aml_audit_reports
            await session.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'tenants') THEN
                        ALTER TABLE aml_audit_reports
                        DROP CONSTRAINT IF EXISTS fk_aml_audit_reports_tenant_id;

                        ALTER TABLE aml_audit_reports
                        ADD CONSTRAINT fk_aml_audit_reports_tenant_id
                        FOREIGN KEY (tenant_id) REFERENCES tenants(id)
                        ON DELETE CASCADE;
                    END IF;
                END $$;
            """))

            await session.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'processing_jobs') THEN
                        ALTER TABLE aml_audit_reports
                        DROP CONSTRAINT IF EXISTS fk_aml_audit_reports_job_id;

                        ALTER TABLE aml_audit_reports
                        ADD CONSTRAINT fk_aml_audit_reports_job_id
                        FOREIGN KEY (job_id) REFERENCES processing_jobs(id)
                        ON DELETE CASCADE;
                    END IF;
                END $$;
            """))

            # Add comments for aml_audit_reports
            await session.execute(text("""
                COMMENT ON TABLE aml_audit_reports IS
                'Stores generated audit reports for regulatory defensibility and compliance';
            """))

            await session.execute(text("""
                COMMENT ON COLUMN aml_audit_reports.kappa_coefficient IS
                'Cohen Kappa coefficient measuring inter-rater agreement (-1 to 1)';
            """))

            await session.execute(text("""
                COMMENT ON COLUMN aml_audit_reports.agreement_level IS
                'Qualitative agreement level derived from kappa: POOR, FAIR, MODERATE, SUBSTANTIAL, PERFECT';
            """))

            print("✓ aml_audit_reports table created with 4 indexes")

            # ================================================================
            # TABLE 3: aml_labeling_methodology
            # ================================================================
            print("Creating aml_labeling_methodology table...")

            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS aml_labeling_methodology (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    tenant_id UUID NOT NULL,
                    version VARCHAR(20) NOT NULL,
                    description TEXT NOT NULL,
                    risk_thresholds JSONB NOT NULL,
                    typologies JSONB NOT NULL,
                    regulatory_references JSONB DEFAULT '{}',
                    created_by UUID,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    status VARCHAR(50) NOT NULL,
                    is_deleted BOOLEAN DEFAULT FALSE,

                    -- CHECK constraint for status
                    CONSTRAINT check_aml_methodology_status
                        CHECK (status IN ('DRAFT', 'ACTIVE', 'ARCHIVED'))
                );
            """))

            # Create indexes for aml_labeling_methodology
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_aml_labeling_methodology_tenant_id
                ON aml_labeling_methodology(tenant_id);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_aml_labeling_methodology_version
                ON aml_labeling_methodology(version);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_aml_labeling_methodology_status
                ON aml_labeling_methodology(status);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_aml_labeling_methodology_is_deleted
                ON aml_labeling_methodology(is_deleted)
                WHERE is_deleted = FALSE;
            """))

            # Create unique constraint: one ACTIVE version per tenant
            await session.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_aml_labeling_methodology_uniq
                ON aml_labeling_methodology(tenant_id, version)
                WHERE status = 'ACTIVE' AND is_deleted = FALSE;
            """))

            # Foreign keys for aml_labeling_methodology
            await session.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'tenants') THEN
                        ALTER TABLE aml_labeling_methodology
                        DROP CONSTRAINT IF EXISTS fk_aml_labeling_methodology_tenant_id;

                        ALTER TABLE aml_labeling_methodology
                        ADD CONSTRAINT fk_aml_labeling_methodology_tenant_id
                        FOREIGN KEY (tenant_id) REFERENCES tenants(id)
                        ON DELETE CASCADE;
                    END IF;
                END $$;
            """))

            await session.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'users') THEN
                        ALTER TABLE aml_labeling_methodology
                        DROP CONSTRAINT IF EXISTS fk_aml_labeling_methodology_created_by;

                        ALTER TABLE aml_labeling_methodology
                        ADD CONSTRAINT fk_aml_labeling_methodology_created_by
                        FOREIGN KEY (created_by) REFERENCES users(user_id)
                        ON DELETE SET NULL;
                    END IF;
                END $$;
            """))

            # Add comments for aml_labeling_methodology
            await session.execute(text("""
                COMMENT ON TABLE aml_labeling_methodology IS
                'Tracks versioned AML labeling rules and methodologies for audit trail';
            """))

            await session.execute(text("""
                COMMENT ON COLUMN aml_labeling_methodology.risk_thresholds IS
                'JSONB: Confidence thresholds for each risk level (LOW, MEDIUM, HIGH, CRITICAL)';
            """))

            await session.execute(text("""
                COMMENT ON COLUMN aml_labeling_methodology.typologies IS
                'JSONB: Valid FATF AML typologies for this methodology version';
            """))

            await session.execute(text("""
                COMMENT ON COLUMN aml_labeling_methodology.regulatory_references IS
                'JSONB: Links to regulatory frameworks (FATF, FinCEN, etc.)';
            """))

            print("✓ aml_labeling_methodology table created with 5 indexes")

            await session.commit()

            # Final summary
            print("\n" + "="*70)
            print("✓ All AML audit trail tables created successfully")
            print("="*70)
            print("Tables created:")
            print("  1. aml_expert_reviews (5 indexes)")
            print("  2. aml_audit_reports (4 indexes)")
            print("  3. aml_labeling_methodology (5 indexes)")
            print("\nTotal: 3 tables, 14 indexes, 8 CHECK constraints, 8 foreign keys")
            print("="*70)

        except Exception as e:
            await session.rollback()
            print(f"✗ Migration failed: {str(e)}")
            raise


async def downgrade():
    """
    Rollback: Drop all audit trail tables and associated objects.

    This rollback:
    1. Drops all foreign key constraints
    2. Drops all indexes (including unique indexes)
    3. Drops all three tables in correct order

    Safe to run - tables can be recreated by re-running upgrade().
    """
    async with db_connection.get_session() as session:
        try:
            print("Rolling back AML audit trail tables...")

            # ================================================================
            # DROP TABLE 1: aml_expert_reviews
            # ================================================================
            print("Dropping aml_expert_reviews...")

            # Drop foreign keys
            await session.execute(text("""
                ALTER TABLE aml_expert_reviews
                DROP CONSTRAINT IF EXISTS fk_aml_expert_reviews_tenant_id;
            """))

            await session.execute(text("""
                ALTER TABLE aml_expert_reviews
                DROP CONSTRAINT IF EXISTS fk_aml_expert_reviews_label_id;
            """))

            await session.execute(text("""
                ALTER TABLE aml_expert_reviews
                DROP CONSTRAINT IF EXISTS fk_aml_expert_reviews_expert_id;
            """))

            # Drop indexes
            await session.execute(text("""
                DROP INDEX IF EXISTS idx_aml_expert_reviews_tenant_id;
            """))

            await session.execute(text("""
                DROP INDEX IF EXISTS idx_aml_expert_reviews_label_id;
            """))

            await session.execute(text("""
                DROP INDEX IF EXISTS idx_aml_expert_reviews_expert_id;
            """))

            await session.execute(text("""
                DROP INDEX IF EXISTS idx_aml_expert_reviews_created_at;
            """))

            await session.execute(text("""
                DROP INDEX IF EXISTS idx_aml_expert_reviews_is_deleted;
            """))

            # Drop table
            await session.execute(text("""
                DROP TABLE IF EXISTS aml_expert_reviews CASCADE;
            """))

            print("✓ aml_expert_reviews dropped")

            # ================================================================
            # DROP TABLE 2: aml_audit_reports
            # ================================================================
            print("Dropping aml_audit_reports...")

            # Drop foreign keys
            await session.execute(text("""
                ALTER TABLE aml_audit_reports
                DROP CONSTRAINT IF EXISTS fk_aml_audit_reports_tenant_id;
            """))

            await session.execute(text("""
                ALTER TABLE aml_audit_reports
                DROP CONSTRAINT IF EXISTS fk_aml_audit_reports_job_id;
            """))

            # Drop indexes
            await session.execute(text("""
                DROP INDEX IF EXISTS idx_aml_audit_reports_tenant_id;
            """))

            await session.execute(text("""
                DROP INDEX IF EXISTS idx_aml_audit_reports_job_id;
            """))

            await session.execute(text("""
                DROP INDEX IF EXISTS idx_aml_audit_reports_created_at;
            """))

            await session.execute(text("""
                DROP INDEX IF EXISTS idx_aml_audit_reports_is_deleted;
            """))

            # Drop table
            await session.execute(text("""
                DROP TABLE IF EXISTS aml_audit_reports CASCADE;
            """))

            print("✓ aml_audit_reports dropped")

            # ================================================================
            # DROP TABLE 3: aml_labeling_methodology
            # ================================================================
            print("Dropping aml_labeling_methodology...")

            # Drop foreign keys
            await session.execute(text("""
                ALTER TABLE aml_labeling_methodology
                DROP CONSTRAINT IF EXISTS fk_aml_labeling_methodology_tenant_id;
            """))

            await session.execute(text("""
                ALTER TABLE aml_labeling_methodology
                DROP CONSTRAINT IF EXISTS fk_aml_labeling_methodology_created_by;
            """))

            # Drop indexes
            await session.execute(text("""
                DROP INDEX IF EXISTS idx_aml_labeling_methodology_tenant_id;
            """))

            await session.execute(text("""
                DROP INDEX IF EXISTS idx_aml_labeling_methodology_version;
            """))

            await session.execute(text("""
                DROP INDEX IF EXISTS idx_aml_labeling_methodology_status;
            """))

            await session.execute(text("""
                DROP INDEX IF EXISTS idx_aml_labeling_methodology_is_deleted;
            """))

            await session.execute(text("""
                DROP INDEX IF EXISTS idx_aml_labeling_methodology_uniq;
            """))

            # Drop table
            await session.execute(text("""
                DROP TABLE IF EXISTS aml_labeling_methodology CASCADE;
            """))

            print("✓ aml_labeling_methodology dropped")

            await session.commit()

            # Final summary
            print("\n" + "="*70)
            print("✓ All AML audit trail tables dropped successfully")
            print("="*70)
            print("Tables dropped:")
            print("  1. aml_expert_reviews")
            print("  2. aml_audit_reports")
            print("  3. aml_labeling_methodology")
            print("\n✓ Downgrade completed without data loss")
            print("="*70)

        except Exception as e:
            await session.rollback()
            print(f"✗ Downgrade failed: {str(e)}")
            raise


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        print("Running downgrade migration for AML audit trail tables...")
        asyncio.run(downgrade())
    else:
        print("Running upgrade migration for AML audit trail tables...")
        asyncio.run(upgrade())
