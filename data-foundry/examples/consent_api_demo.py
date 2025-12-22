#!/usr/bin/env python3
"""
Consent API Demo

Demonstrates usage of the GDPR-compliant consent management API endpoints.
This example shows the complete consent lifecycle from grant to withdrawal.
"""

import json
import time
from datetime import datetime, timezone
from typing import Dict, Any

import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

# Configuration
BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api/v1"

# Initialize rich console for pretty output
console = Console()


class ConsentAPIClient:
    """Client for interacting with the Consent API."""

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.api_base = f"{base_url}/api/v1"
        self.token = None
        self.headers = {}

    def authenticate(self) -> None:
        """Get authentication token."""
        console.print("\n🔐 [bold blue]Authenticating...[/bold blue]")

        try:
            response = requests.get(f"{self.base_url}/test-token")
            response.raise_for_status()

            token_data = response.json()
            self.token = token_data["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}

            console.print("✅ [green]Authentication successful![/green]")
            console.print(f"   Token expires in: {token_data.get('expires_in', 24)} hours")

        except requests.RequestException as e:
            console.print(f"❌ [red]Authentication failed: {e}[/red]")
            raise

    def grant_consent(self, user_id: str, consent_type: str, consent_text: str,
                     metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Grant consent for a user."""
        console.print(f"\n📝 [bold blue]Granting consent for user {user_id}...[/bold blue]")

        if metadata is None:
            metadata = {
                "ip": "192.168.1.100",
                "user_agent": "Consent Demo Client",
                "purpose": "demo_purpose",
                "retention_period": "demo_period",
                "source": "demo_script"
            }

        payload = {
            "user_id": user_id,
            "consent_type": consent_type,
            "consent_text": consent_text,
            "metadata": metadata
        }

        try:
            response = requests.post(
                f"{self.api_base}/consent/grant",
                json=payload,
                headers=self.headers
            )
            response.raise_for_status()

            result = response.json()
            console.print("✅ [green]Consent granted successfully![/green]")
            console.print(f"   Consent ID: {result['data'].get('consent_id')}")
            console.print(f"   Status: {result['data'].get('status')}")

            return result

        except requests.RequestException as e:
            console.print(f"❌ [red]Failed to grant consent: {e}[/red]")
            if e.response:
                console.print(f"   Error: {e.response.json().get('detail', 'Unknown error')}")
            raise

    def verify_consent(self, user_id: str, consent_type: str) -> Dict[str, Any]:
        """Verify if user has active consent."""
        console.print(f"\n🔍 [bold blue]Verifying consent for user {user_id}...[/bold blue]")

        try:
            response = requests.get(
                f"{self.api_base}/consent/verify/{user_id}/{consent_type}",
                headers=self.headers
            )
            response.raise_for_status()

            result = response.json()

            if result["has_consent"]:
                console.print("✅ [green]User has active consent[/green]")
                console.print(f"   Granted at: {result.get('granted_at')}")
                console.print(f"   Status: {result.get('status')}")
            else:
                console.print("❌ [red]No active consent found[/red]")

            return result

        except requests.RequestException as e:
            console.print(f"❌ [red]Failed to verify consent: {e}[/red]")
            raise

    def get_user_consents(self, user_id: str) -> Dict[str, Any]:
        """Get all consents for a user."""
        console.print(f"\n📋 [bold blue]Getting consents for user {user_id}...[/bold blue]")

        try:
            response = requests.get(
                f"{self.api_base}/consent/user/{user_id}",
                headers=self.headers
            )
            response.raise_for_status()

            consents = response.json()

            if consents:
                console.print(f"✅ [green]Found {len(consents)} consent(s)[/green]")

                # Display in table
                table = Table(title=f"Consents for {user_id}")
                table.add_column("ID", style="cyan")
                table.add_column("Type", style="magenta")
                table.add_column("Status", style="green")
                table.add_column("Granted At", style="blue")

                for consent in consents:
                    status_style = "green" if consent["status"] == "active" else "red"
                    table.add_row(
                        str(consent["id"]),
                        consent["consent_type"],
                        f"[{status_style}]{consent['status']}[/{status_style}]",
                        consent["granted_at"][:19]  # Remove microseconds
                    )

                console.print(table)
            else:
                console.print("ℹ️ [yellow]No consents found for user[/yellow]")

            return {"consents": consents}

        except requests.RequestException as e:
            console.print(f"❌ [red]Failed to get user consents: {e}[/red]")
            raise

    def withdraw_consent(self, user_id: str, consent_type: str, reason: str = None) -> Dict[str, Any]:
        """Withdraw consent for a user."""
        console.print(f"\n🚫 [bold blue]Withdrawing consent for user {user_id}...[/bold blue]")

        payload = {
            "user_id": user_id,
            "consent_type": consent_type,
            "reason": reason or "Withdrawn via demo",
            "metadata": {
                "ip": "192.168.1.100",
                "user_agent": "Consent Demo Client"
            }
        }

        try:
            response = requests.post(
                f"{self.api_base}/consent/withdraw",
                json=payload,
                headers=self.headers
            )
            response.raise_for_status()

            result = response.json()
            console.print("✅ [green]Consent withdrawn successfully![/green]")
            console.print(f"   Withdrawn at: {result['data'].get('withdrawn_at')}")

            return result

        except requests.RequestException as e:
            console.print(f"❌ [red]Failed to withdraw consent: {e}[/red]")
            if e.response:
                console.print(f"   Error: {e.response.json().get('detail', 'Unknown error')}")
            raise

    def object_to_processing(self, user_id: str, consent_type: str, reason: str,
                           category: str = "general") -> Dict[str, Any]:
        """Object to processing (GDPR Article 21)."""
        console.print(f"\n⚖️ [bold blue]Recording objection for user {user_id}...[/bold blue]")

        payload = {
            "user_id": user_id,
            "consent_type": consent_type,
            "reason": reason,
            "category": category,
            "metadata": {
                "ip": "192.168.1.100",
                "user_agent": "Consent Demo Client"
            }
        }

        try:
            response = requests.post(
                f"{self.api_base}/consent/object",
                json=payload,
                headers=self.headers
            )
            response.raise_for_status()

            result = response.json()
            console.print("✅ [green]Objection recorded successfully![/green]")
            console.print(f"   Objection ID: {result.get('objection_id')}")
            console.print(f"   Category: {result.get('category')}")

            return result

        except requests.RequestException as e:
            console.print(f"❌ [red]Failed to record objection: {e}[/red]")
            raise

    def get_consent_history(self, user_id: str, page: int = 1, per_page: int = 10) -> Dict[str, Any]:
        """Get consent history for a user."""
        console.print(f"\n📜 [bold blue]Getting consent history for user {user_id}...[/bold blue]")

        try:
            response = requests.get(
                f"{self.api_base}/consent/user/{user_id}/history",
                params={"page": page, "per_page": per_page},
                headers=self.headers
            )
            response.raise_for_status()

            history = response.json()

            console.print(f"✅ [green]Retrieved {len(history['records'])} records[/green]")
            console.print(f"   Total records: {history['total']}")
            console.print(f"   Page: {history['page']} of {history['total'] // history['per_page'] + 1}")

            # Display in table
            table = Table(title=f"Consent History for {user_id}")
            table.add_column("ID", style="cyan")
            table.add_column("Type", style="magenta")
            table.add_column("Status", style="green")
            table.add_column("Granted", style="blue")
            table.add_column("Withdrawn", style="red")

            for record in history["records"]:
                granted = record["granted_at"][:19]
                withdrawn = record.get("withdrawn_at", "")[:19]
                status_style = "green" if record["status"] == "active" else "red"

                table.add_row(
                    str(record["id"]),
                    record["consent_type"],
                    f"[{status_style}]{record['status']}[/{status_style}]",
                    granted,
                    withdrawn or "-"
                )

            console.print(table)

            return history

        except requests.RequestException as e:
            console.print(f"❌ [red]Failed to get consent history: {e}[/red]")
            raise


def main():
    """Run the consent API demo."""
    # Print welcome message
    console.print(Panel.fit(
        "[bold cyan]Consent API Demo[/bold cyan]\n"
        "Demonstrating GDPR-compliant consent management",
        border_style="blue"
    ))

    # Initialize client
    client = ConsentAPIClient()

    try:
        # Authenticate
        client.authenticate()

        # Demo user
        demo_user = f"demo_user_{int(time.time())}"

        # 1. Grant consent for data processing
        console.print("\n[bold cyan]=== Step 1: Grant Data Processing Consent ===[/bold cyan]")
        data_processing_consent = (
            "I consent to the processing of my personal data for the purpose of improving "
            "services. This includes analysis of usage patterns, personalization of content, "
            "and storage of data for a period of 2 years. I understand that I can withdraw "
            "this consent at any time."
        )
        client.grant_consent(
            user_id=demo_user,
            consent_type="data_processing",
            consent_text=data_processing_consent
        )

        # 2. Verify the consent
        console.print("\n[bold cyan]=== Step 2: Verify Consent Status ===[/bold cyan]")
        client.verify_consent(demo_user, "data_processing")

        # 3. Grant marketing consent
        console.print("\n[bold cyan]=== Step 3: Grant Marketing Consent ===[/bold cyan]")
        marketing_consent = (
            "I consent to receive marketing communications via email about products, "
            "services, and promotions that may be of interest to me. I understand that "
            "I can unsubscribe at any time and that my data will not be shared with "
            "third parties for marketing purposes."
        )
        client.grant_consent(
            user_id=demo_user,
            consent_type="marketing",
            consent_text=marketing_consent
        )

        # 4. Get all user consents
        console.print("\n[bold cyan]=== Step 4: List All User Consents ===[/bold cyan]")
        client.get_user_consents(demo_user)

        # 5. Object to analytics processing
        console.print("\n[bold cyan]=== Step 5: Object to Analytics Processing ===[/bold cyan]")
        client.object_to_processing(
            user_id=demo_user,
            consent_type="analytics",
            reason="I do not want my data used for analytics purposes",
            category="analytics"
        )

        # 6. Withdraw marketing consent
        console.print("\n[bold cyan]=== Step 6: Withdraw Marketing Consent ===[/bold cyan]")
        client.withdraw_consent(
            user_id=demo_user,
            consent_type="marketing",
            reason="Too many emails"
        )

        # 7. Get consent history
        console.print("\n[bold cyan]=== Step 7: View Consent History ===[/bold cyan]")
        client.get_consent_history(demo_user)

        # Final verification
        console.print("\n[bold cyan]=== Final Verification ===[/bold cyan]")
        client.verify_consent(demo_user, "data_processing")
        client.verify_consent(demo_user, "marketing")

        console.print("\n✅ [bold green]Demo completed successfully![/bold green]")

    except Exception as e:
        console.print(f"\n❌ [bold red]Demo failed: {e}[/bold red]")
        console.print("\n[yellow]Make sure the API server is running at http://localhost:8000[/yellow]")


if __name__ == "__main__":
    main()