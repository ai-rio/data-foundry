"""
Regulatory Reference API Module

Provides regulatory context for AML (Anti-Money Laundering) service.
Exposes endpoints that return regulatory framework information used
in AML labeling methodology.

This module serves as a reference for customers to understand the
regulatory foundations of the AML labeling service, including:
- FATF (Financial Action Task Force) recommendations
- FinCEN (US Financial Crimes Enforcement Network) guidelines
- EU 6AMLD/AMLA (European Union Anti-Money Laundering Directive)
- BCB/COAF (Brazilian Central Bank regulations)

Implementation: P01-016
"""

from .router import router

__all__ = ["router"]
