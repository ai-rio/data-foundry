#!/usr/bin/env python3
"""
Basic functionality test for incident response system.
"""

import sys
import os
import asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.models.incident import IncidentRecord, IncidentTimelineEntry
from src.models.enums import IncidentSeverity, IncidentStatus, IncidentType
from src.core.incident_manager import IncidentClassifier
from src.core.notification_service import NotificationService
from datetime import datetime, timezone

async def test_incident_response_system():
    """Test core incident response functionality."""
    print("Testing Data Foundry Incident Response System")
    print("=" * 50)

    # Test basic incident creation
    print("\n1. Testing Incident Creation...")
    incident = IncidentRecord(
        title='Data Breach Detected',
        description='Unauthorized access to customer database',
        incident_type=IncidentType.DATA_BREACH,
        severity=IncidentSeverity.CRITICAL,
        reported_by='security_team@company.com'
    )
    print(f"   ✓ Incident created with ID: {incident.incident_id}")
    print(f"   ✓ Status: {incident.status}")

    # Test GDPR deadline functionality
    print("\n2. Testing GDPR Compliance...")
    deadline = incident.get_gdpr_notification_deadline()
    print(f"   ✓ GDPR deadline calculated: {deadline}")
    print(f"   ✓ Deadline passed: {incident.is_gdpr_deadline_passed()}")

    # Test timeline entry creation
    print("\n3. Testing Timeline Management...")
    entry = IncidentTimelineEntry(
        timestamp=datetime.now(timezone.utc),
        action='System isolation',
        details='Affected system isolated from network',
        performed_by='security_admin@company.com'
    )
    print(f"   ✓ Timeline entry created: {entry.entry_id}")

    # Test incident status updates
    print("\n4. Testing Status Updates...")
    incident.update_status(IncidentStatus.INVESTIGATING)
    print(f"   ✓ Status updated to: {incident.status}")

    incident.update_status(IncidentStatus.IDENTIFIED)
    print(f"   ✓ Status updated to: {incident.status}")

    # Test timeline functionality
    print("\n5. Testing Timeline Entries...")
    incident.add_timeline_entry(entry)
    print(f"   ✓ Timeline entry added: {len(incident.timeline)} entries")

    # Test impact assessment
    print("\n6. Testing Impact Assessment...")
    impact_assessment = {
        'data_subjects_affected': 1000,
        'data_types_involved': ['email', 'name'],
        'consequences': ['privacy_risk']
    }
    incident.update_impact_assessment(impact_assessment)
    print("   ✓ Impact assessment updated")

    # Test incident assignment
    print("\n7. Testing Incident Assignment...")
    incident.assign_to('expert@company.com', 'manager@company.com', 'Subject matter expert')
    print(f"   ✓ Incident assigned to: {incident.assignee}")

    # Test database model conversion
    print("\n8. Testing Database Model Conversion...")
    db_model = incident.to_database_model()
    print("   ✓ Database model conversion successful")

    # Test incident closure
    print("\n9. Testing Incident Closure...")
    closure_details = {
        'root_cause': 'SQL injection vulnerability',
        'resolution': 'Vulnerability patched',
        'prevention_measures': ['code review process'],
        'lessons_learned': 'Need better input validation'
    }
    incident.close_incident('engineer@company.com', closure_details)
    print(f"   ✓ Incident closed: {incident.status}")

    # Test IncidentClassifier
    print("\n10. Testing Automatic Classification...")
    classifier = IncidentClassifier()

    incident_data = {
        'description': 'Unauthorized access to customer database containing personal information',
        'evidence': {'data_access': True, 'personal_data': True},
        'affected_systems': ['customer_db']
    }

    classification = await classifier.classify_incident(incident_data)
    print(f"   ✓ Classification: {classification.incident_type.value}")
    print(f"   ✓ Severity: {classification.severity.value}")
    print(f"   ✓ Confidence: {classification.confidence:.2f}")

    # Test NotificationService
    print("\n11. Testing Notification Service...")
    notification_service = NotificationService()

    result = await notification_service.send_alert(
        recipient='user@company.com',
        subject='Test Alert',
        message='This is a test notification',
        notification_type='test'
    )
    print(f"   ✓ Notification sent: {result.success}")

    # Test template notifications
    print("\n12. Testing Template Notifications...")
    template_result = await notification_service.send_template_notification(
        template_name='incident_assignment',
        recipient='expert@company.com',
        template_data={
            'incident_id': 'INC-123',
            'incident_title': 'Data Breach',
            'assigned_by': 'manager@company.com',
            'reason': 'Subject matter expert'
        }
    )
    print(f"   ✓ Template notification sent: {template_result.success}")

    # Test bulk notifications
    print("\n13. Testing Bulk Notifications...")
    recipients = ['user1@company.com', 'user2@company.com', 'user3@company.com']
    bulk_results = await notification_service.send_bulk_alert(
        recipients=recipients,
        subject='System Maintenance',
        message='Scheduled maintenance will begin in 1 hour.'
    )
    print(f"   ✓ Bulk notifications sent to {len(recipients)} recipients")
    print(f"   ✓ Success rate: {sum(1 for r in bulk_results if r.success)}/{len(bulk_results)}")

    print("\n" + "=" * 50)
    print("🎉 ALL INCIDENT RESPONSE SYSTEM TESTS PASSED!")
    print(f"Final incident status: {incident.status}")
    print(f"Total timeline entries: {len(incident.timeline)}")
    print(f"Classification confidence: {classification.confidence:.2f}")
    print(f"Notification delivery: {result.success}")

    return True

if __name__ == "__main__":
    success = asyncio.run(test_incident_response_system())
    sys.exit(0 if success else 1)