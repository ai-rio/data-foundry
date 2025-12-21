#!/usr/bin/env python3
"""
Log Security Scanner

This script scans logs and configuration files for exposed secrets and provides
a comprehensive security report on any sensitive data found.
"""

import os
import sys
import re
import json
from pathlib import Path
from typing import List, Dict, Tuple

# Secret patterns to detect
SECRET_PATTERNS = {
    'api_keys': [
        r'sk-[a-zA-Z0-9]{20,}',  # OpenAI API keys
        r'sk-or-v1-[a-zA-Z0-9-]{8,}',  # OpenRouter keys
        r'github_pat_[a-zA-Z0-9_]{20,}',  # GitHub PAT
        r'ghp_[a-zA-Z0-9]{36}',  # GitHub tokens
        r'[a-zA-Z0-9]{32}-oauth2',  # OAuth2 tokens
    ],
    'database_urls': [
        r'postgresql://[^:]+:[^@]+@[^/]+/[^\s]+',  # PostgreSQL URLs
        r'mysql://[^:]+:[^@]+@[^/]+/[^\s]+',  # MySQL URLs
        r'mongodb://[^:]+:[^@]+@[^/]+/[^\s]+',  # MongoDB URLs
    ],
    'passwords': [
        r'password["\']?\s*[:=]\s*["\']?([^"\'\s]{8,})',
        r'secret["\']?\s*[:=]\s*["\']?([^"\'\s]{8,})',
        r'token["\']?\s*[:=]\s*["\']?([^"\'\s]{8,})',
    ],
    'pii': [
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email
        r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
        r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',  # Credit card
        r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b',  # Phone number
    ],
    'encryption_keys': [
        r'SECRET_MANAGER_KEY=([A-Za-z0-9+/]{40,}=*)',
        r'ENCRYPTION_KEY=([A-Za-z0-9+/]{40,}=*)',
        r'PRIVATE_KEY-----BEGIN[^\-]+-----END PRIVATE KEY-----',
    ]
}

def scan_file_for_secrets(file_path: Path) -> Dict[str, List[Tuple[int, str, str]]]:
    """Scan a single file for secrets."""
    secrets_found = {}

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        for line_num, line in enumerate(lines, 1):
            for category, patterns in SECRET_PATTERNS.items():
                for pattern in patterns:
                    matches = re.finditer(pattern, line, re.IGNORECASE)
                    for match in matches:
                        if category not in secrets_found:
                            secrets_found[category] = []

                        # Mask the actual secret for reporting
                        secret_value = match.group(0)
                        if len(secret_value) > 8:
                            masked_secret = secret_value[:4] + '*' * (len(secret_value) - 8) + secret_value[-4:]
                        else:
                            masked_secret = '*' * len(secret_value)

                        secrets_found[category].append((line_num, masked_secret, line.strip()[:100]))

    except Exception as e:
        print(f"Error scanning {file_path}: {e}")

    return secrets_found

def scan_directory_for_secrets(directory: Path, extensions: List[str] = None) -> Dict[str, Dict]:
    """Scan a directory for files containing secrets."""
    if extensions is None:
        extensions = ['.log', '.txt', '.env', '.config', '.conf', '.json', '.yaml', '.yml', '.py', '.js', '.ts']

    results = {}

    for file_path in directory.rglob('*'):
        if file_path.is_file() and file_path.suffix in extensions:
            # Skip .git and __pycache__ directories
            if '.git' in file_path.parts or '__pycache__' in file_path.parts:
                continue

            # Skip our encrypted files (they're supposed to have secrets)
            if file_path.name in ['.env.encrypted', '.env.encryption']:
                continue

            secrets = scan_file_for_secrets(file_path)
            if secrets:
                results[str(file_path)] = secrets

    return results

def check_environment_variables() -> Dict[str, str]:
    """Check environment variables for exposed secrets."""
    exposed_secrets = {}

    for key, value in os.environ.items():
        # Check for potential secrets in environment variables
        if any(keyword in key.upper() for keyword in ['API_KEY', 'SECRET', 'PASSWORD', 'TOKEN', 'KEY']):
            # Check if it's not encrypted
            if not key.endswith('_ENCRYPTED') and len(value) > 8:
                # Simple pattern check for API keys
                if any(pattern in value.lower() for pattern in ['sk-', 'github_pat_', 'ghp_']):
                    exposed_secrets[key] = value[:4] + '*' * (len(value) - 8) + value[-4:]

    return exposed_secrets

def generate_security_report(scan_results: Dict, env_secrets: Dict) -> Dict:
    """Generate a comprehensive security report."""
    total_issues = sum(len(secrets) for file_secrets in scan_results.values() for secrets in file_secrets.values())
    total_issues += len(env_secrets)

    report = {
        'scan_summary': {
            'files_scanned': len(scan_results),
            'total_secrets_found': total_issues,
            'environment_secrets': len(env_secrets),
            'critical_issues': 0,
            'warning_issues': 0
        },
        'categories': {
            'api_keys': 0,
            'database_urls': 0,
            'passwords': 0,
            'pii': 0,
            'encryption_keys': 0
        },
        'files_with_secrets': {},
        'environment_exposure': env_secrets,
        'recommendations': []
    }

    # Count issues by category
    for file_path, file_secrets in scan_results.items():
        report['files_with_secrets'][file_path] = file_secrets
        for category, secrets in file_secrets.items():
            report['categories'][category] = report['categories'].get(category, 0) + len(secrets)

    # Add environment secrets to categories
    for key in env_secrets:
        if 'API_KEY' in key:
            report['categories']['api_keys'] += 1
        elif 'PASSWORD' in key or 'SECRET' in key:
            report['categories']['passwords'] += 1

    # Count critical vs warning issues
    report['scan_summary']['critical_issues'] = (
        report['categories']['api_keys'] +
        report['categories']['database_urls'] +
        report['categories']['encryption_keys']
    )
    report['scan_summary']['warning_issues'] = (
        report['categories']['passwords'] +
        report['categories']['pii']
    )

    # Generate recommendations
    if report['categories']['api_keys'] > 0:
        report['recommendations'].append("CRITICAL: API keys found in plaintext. Use SecretManager to encrypt all API keys.")

    if report['categories']['database_urls'] > 0:
        report['recommendations'].append("CRITICAL: Database URLs with passwords found in plaintext. Use secure connection strings.")

    if report['categories']['encryption_keys'] > 0:
        report['recommendations'].append("CRITICAL: Encryption keys found in files. Store keys in secure key management service.")

    if report['categories']['passwords'] > 0:
        report['recommendations'].append("WARNING: Passwords found in plaintext. Use environment variables with encryption.")

    if report['categories']['pii'] > 0:
        report['recommendations'].append("WARNING: Personally Identifiable Information (PII) found. Implement data masking.")

    if len(env_secrets) > 0:
        report['recommendations'].append("CRITICAL: Secrets found in environment variables. Use encrypted environment variables.")

    return report

def main():
    """Main log scanning function."""
    print("🔍 Starting comprehensive log security scan...")
    print("=" * 50)

    # Scan current directory for secrets
    current_dir = Path('.')
    scan_results = scan_directory_for_secrets(current_dir)

    # Check environment variables
    print("🔍 Checking environment variables...")
    env_secrets = check_environment_variables()

    # Generate report
    report = generate_security_report(scan_results, env_secrets)

    # Print results
    print(f"\n📊 SECURITY SCAN RESULTS")
    print(f"Files scanned: {report['scan_summary']['files_scanned']}")
    print(f"Total secrets found: {report['scan_summary']['total_secrets']}")
    print(f"Critical issues: {report['scan_summary']['critical_issues']}")
    print(f"Warning issues: {report['scan_summary']['warning_issues']}")

    # Category breakdown
    print(f"\n📋 SECRETS BY CATEGORY:")
    for category, count in report['categories'].items():
        if count > 0:
            print(f"  {category.replace('_', ' ').title()}: {count}")

    # Files with secrets
    if report['files_with_secrets']:
        print(f"\n📁 FILES WITH SECRETS:")
        for file_path, file_secrets in report['files_with_secrets'].items():
            print(f"\n  📄 {file_path}")
            for category, secrets in file_secrets.items():
                print(f"    {category}: {len(secrets)} occurrences")
                for line_num, secret, context in secrets[:3]:  # Show first 3
                    print(f"      Line {line_num}: {secret} (context: {context}...)")

    # Environment exposure
    if report['environment_exposure']:
        print(f"\n🌍 ENVIRONMENT SECRETS EXPOSED:")
        for key, masked_value in report['environment_exposure'].items():
            print(f"  {key}: {masked_value}")

    # Recommendations
    if report['recommendations']:
        print(f"\n💡 SECURITY RECOMMENDATIONS:")
        for i, rec in enumerate(report['recommendations'], 1):
            print(f"  {i}. {rec}")

    # Overall security score
    max_possible_issues = 20  # Adjust based on expected issues
    security_score = max(0, 100 - (report['scan_summary']['total_secrets'] * 5))

    print(f"\n🎯 SECURITY SCORE: {security_score}/100")
    if security_score >= 90:
        print("✅ EXCELLENT - Very secure configuration")
    elif security_score >= 75:
        print("⚠️  GOOD - Some security improvements needed")
    elif security_score >= 50:
        print("⚠️  FAIR - Significant security issues found")
    else:
        print("❌ POOR - Critical security vulnerabilities found")

    # Save detailed report
    report_file = 'security_scan_report.json'
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n📄 Detailed report saved to: {report_file}")

    return 0 if report['scan_summary']['critical_issues'] == 0 else 1

if __name__ == "__main__":
    sys.exit(main())