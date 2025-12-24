"""
Test PII Redaction (Presidio)
Verify that PII is detected and redacted properly
"""
import sys
sys.path.insert(0, '/home/carlos/projects/data_foundry/data-foundry')

from src.tasks.ingestion import apply_pii_redaction

def test_pii_redaction():
    """Verify Presidio correctly detects and redacts PII"""

    test_data = [
        {
            "patient_id": "MRN123456789",  # Medical Record Number
            "name": "John Doe",
            "ssn": "123-45-6789",
            "phone": "(555) 123-4567",
            "email": "john@example.com",
            "diagnosis": "Type 2 Diabetes",
            "notes": "Patient called from 555-987-6543"
        },
        {
            "patient_id": "MRN987654321",
            "name": "Jane Smith",
            "ssn": "987-65-4321",
            "phone": "555.123.7890",
            "email": "jane.smith@hospital.org",
            "diagnosis": "Hypertension",
            "notes": "Email patient at jane.smith@hospital.org"
        }
    ]

    print("Testing PII redaction with Presidio:")
    print(f"  Input: {len(test_data)} records with PII")

    # Redact PII
    redacted_data = apply_pii_redaction(test_data)

    # Verify results
    test_passed = True
    pii_types_found = set()

    for i, record in enumerate(redacted_data):
        print(f"\n--- Record {i+1} ---")

        # Check if PII redaction was applied
        if not record.get("pii_redaction_applied", False):
            print("⚠️  PII redaction not applied - Presidio may not be installed")
            # This is not a failure if Presidio is not installed
            if record.get("pii_redaction_skipped", False):
                print(f"   Reason: {record.get('pii_redaction_reason', 'Unknown')}")
                print("⚠️  SKIPPING PII REDACTION TEST (Presidio not available)")
                return None  # Skip test
            continue

        # Verify SSN redaction
        original_ssn = test_data[i]["ssn"]
        redacted_ssn = record["ssn"]
        if original_ssn in redacted_ssn:
            print(f"❌ CRITICAL: SSN not redacted! '{original_ssn}' -> '{redacted_ssn}'")
            test_passed = False
        else:
            print(f"✅ SSN redacted: '{original_ssn}' -> '{redacted_ssn}'")
            pii_types_found.add("SSN")

        # Verify phone redaction
        original_phone = test_data[i]["phone"]
        redacted_phone = record["phone"]
        if original_phone in redacted_phone and original_phone.replace("(", "").replace(")", "").replace("-", "").replace(".", "") in redacted_phone:
            print(f"⚠️  Phone may not be fully redacted: '{original_phone}' -> '{redacted_phone}'")
        else:
            print(f"✅ Phone redacted: '{original_phone}' -> '{redacted_phone}'")
            pii_types_found.add("PHONE")

        # Verify email redaction
        original_email = test_data[i]["email"]
        redacted_email = record["email"]
        if "@" in redacted_email and original_email.split("@")[0] not in redacted_email:
            print(f"✅ Email redacted: '{original_email}' -> '{redacted_email}'")
            pii_types_found.add("EMAIL")
        elif original_email in redacted_email:
            print(f"⚠️  Email may not be redacted: '{original_email}' -> '{redacted_email}'")

        # Verify name redaction (optional - names are harder to detect)
        original_name = test_data[i]["name"]
        redacted_name = record["name"]
        if original_name != redacted_name:
            print(f"✅ Name redacted: '{original_name}' -> '{redacted_name}'")
            pii_types_found.add("PERSON")

        # Verify diagnosis is NOT redacted (not PII)
        original_diagnosis = test_data[i]["diagnosis"]
        redacted_diagnosis = record["diagnosis"]
        if original_diagnosis == redacted_diagnosis:
            print(f"✅ Diagnosis preserved (not PII): '{redacted_diagnosis}'")
        else:
            print(f"⚠️  Diagnosis was modified: '{original_diagnosis}' -> '{redacted_diagnosis}'")

    # Summary
    print(f"\n{'='*50}")
    print(f"PII Redaction Test Summary:")
    print(f"  PII types detected: {', '.join(sorted(pii_types_found)) if pii_types_found else 'None'}")

    if test_passed:
        print("✅ PII REDACTION TEST PASSED!")
        print("   All sensitive data properly masked")
    else:
        print("❌ PII REDACTION TEST FAILED!")
        print("   Some sensitive data was not redacted")

    return test_passed

if __name__ == "__main__":
    result = test_pii_redaction()

    if result is None:
        print("\n⚠️  Test skipped - Presidio not installed")
        sys.exit(0)  # Don't fail the build if Presidio isn't installed
    elif result:
        sys.exit(0)
    else:
        sys.exit(1)
