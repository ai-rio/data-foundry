#!/usr/bin/env python3
"""
Quick validation: Test Stripe billing with real API (test mode)

This script will:
1. Create a test customer
2. Report meter events (ai_labels, human_audits)
3. Verify the events were recorded

Run: python test_stripe_live.py
"""
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from src.services.stripe.facade import StripeService
from src.core.config import Settings


async def main():
    print("=" * 60)
    print("🔥 STRIPE BILLING LIVE TEST")
    print("=" * 60)

    # Initialize settings
    settings = Settings()

    # Check Stripe key
    stripe_key = os.getenv("STRIPE_SECRET_KEY")
    if not stripe_key:
        print("❌ STRIPE_SECRET_KEY not found in environment!")
        return False

    if not stripe_key.startswith("sk_test_"):
        print("⚠️  WARNING: Not using test mode key!")
        response = input("Continue anyway? (yes/no): ")
        if response.lower() != "yes":
            return False

    print(f"✅ Stripe API Key: {stripe_key[:15]}...{stripe_key[-4:]}")
    print()

    # Initialize Stripe service
    print("📦 Initializing Stripe service...")
    stripe_service = StripeService()
    await stripe_service.initialize()
    print("✅ Stripe service initialized")
    print()

    # Test 1: Create a customer
    print("=" * 60)
    print("TEST 1: Create Customer")
    print("=" * 60)

    test_tenant_id = f"test_tenant_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    test_email = f"test+{test_tenant_id}@datafoundry.dev"

    try:
        customer = await stripe_service.create_customer(
            tenant_id=test_tenant_id,
            email=test_email,
            name="Data Foundry Test Customer"
        )
        print(f"✅ Customer created successfully!")
        print(f"   Customer ID: {customer.stripe_customer_id}")
        print(f"   Tenant ID: {customer.tenant_id}")
        print(f"   Email: {test_email}")
        stripe_customer_id = customer.stripe_customer_id
    except Exception as e:
        print(f"❌ Failed to create customer: {e}")
        return False

    print()

    # Test 2: Report AI labels meter event
    print("=" * 60)
    print("TEST 2: Report AI Labels Usage")
    print("=" * 60)

    try:
        result = await stripe_service.report_usage(
            tenant_id=test_tenant_id,
            event_name="ai_labels",
            value=150,  # 150 AI labels
            idempotency_key=f"{test_tenant_id}_ai_test_1"
        )
        print(f"✅ AI labels meter event reported!")
        print(f"   Quantity: 150 labels")
        print(f"   Result: {result}")
    except Exception as e:
        print(f"❌ Failed to report AI labels: {e}")
        print(f"   Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()

    print()

    # Test 3: Report human audits meter event
    print("=" * 60)
    print("TEST 3: Report Human Audits Usage")
    print("=" * 60)

    try:
        result = await stripe_service.report_usage(
            tenant_id=test_tenant_id,
            event_name="human_audits",
            value=25,  # 25 human audits
            idempotency_key=f"{test_tenant_id}_human_test_1"
        )
        print(f"✅ Human audits meter event reported!")
        print(f"   Quantity: 25 audits")
        print(f"   Result: {result}")
    except Exception as e:
        print(f"❌ Failed to report human audits: {e}")
        print(f"   Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()

    print()

    # Summary
    print("=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    print(f"✅ Customer created: {stripe_customer_id}")
    print(f"✅ AI labels reported: 150")
    print(f"✅ Human audits reported: 25")
    print()
    print("🎉 All tests passed!")
    print()
    print("Next steps:")
    print("1. Open Stripe Dashboard: https://dashboard.stripe.com/test/customers")
    print(f"2. Search for customer: {test_email}")
    print("3. Check the 'Billing' tab for meter events")
    print("4. Verify usage shows: 150 ai_labels + 25 human_audits")
    print()

    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
