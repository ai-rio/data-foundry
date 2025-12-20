"""
Prompt Templates for Data Foundry

This module provides functionality for loading and rendering YAML-based prompt templates.
Templates use Jinja2 for dynamic content generation and include structured response formats.

Features:
- YAML-based template definition
- Jinja2 template rendering
- Variable validation
- Response format specification
- Template metadata management
"""

from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml
from jinja2 import Environment, FileSystemLoader, Template, TemplateSyntaxError, meta
import json

from ..validation import (
    validate_template_syntax,
    validate_template_variables,
    validate_template_consistency,
)


class TemplateType(str, Enum):
    """Enumeration of available template types."""

    DATA_CLASSIFICATION = "data_classification"
    PII_DETECTION = "pii_detection"
    CONFIDENCE_ASSESSMENT = "confidence_assessment"


class DataClassificationTemplate:
    """Constants and metadata for the data classification template."""

    FILENAME = "data_classification.yaml"

    # This will be populated when the template is loaded
    METADATA: Dict[str, Any] = {}


# Template cache for performance
_template_cache: Dict[str, Dict[str, Any]] = {}
_jinja_env: Optional[Environment] = None


def _get_template_dir() -> Path:
    """Get the directory containing template files."""
    return Path(__file__).parent.absolute()


def _get_jinja_env() -> Environment:
    """Get or create a Jinja2 environment for template rendering."""
    global _jinja_env

    if _jinja_env is None:
        template_dir = _get_template_dir()
        _jinja_env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

        # Add custom filters
        _jinja_env.filters['tojson'] = json.dumps

    return _jinja_env


def load_template(template_name: str, use_cache: bool = True) -> Dict[str, Any]:
    """
    Load a template from YAML file.

    Args:
        template_name: Name of the template file
        use_cache: Whether to use cached template if available

    Returns:
        Dictionary containing template metadata, content, and response format

    Raises:
        FileNotFoundError: If template file doesn't exist
        yaml.YAMLError: If template file is invalid YAML
        ValueError: If template structure is invalid
    """
    if use_cache and template_name in _template_cache:
        return _template_cache[template_name]

    template_path = _get_template_dir() / template_name

    if not template_path.exists():
        raise FileNotFoundError(f"Template file not found: {template_path}")

    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            template_data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in template {template_name}: {e}")

    # Validate template structure
    _validate_template_structure(template_data, template_name)

    # Validate Jinja2 syntax
    validate_template_syntax(template_data.get('template', ''))

    # Cache the template
    if use_cache:
        _template_cache[template_name] = template_data

    # Update metadata constants if this is the data classification template
    if template_name == DataClassificationTemplate.FILENAME:
        DataClassificationTemplate.METADATA = template_data.get('metadata', {})

    return template_data


def render_template(template_name: str, variables: Dict[str, Any]) -> str:
    """
    Render a template with the provided variables.

    Args:
        template_name: Name of the template file
        variables: Dictionary of variables to substitute in the template

    Returns:
        Rendered template string

    Raises:
        FileNotFoundError: If template file doesn't exist
        ValueError: If template syntax is invalid or variables are missing
    """
    template_data = load_template(template_name)

    # Validate required variables
    validate_template_variables(
        template_data.get('template', ''),
        variables,
        template_data.get('metadata', {}).get('required_variables', [])
    )

    # Render the template
    jinja_template = _get_jinja_env().from_string(template_data['template'])

    try:
        rendered = jinja_template.render(**variables)
    except Exception as e:
        raise ValueError(f"Error rendering template {template_name}: {e}")

    return rendered


def get_template_metadata(template_name: str) -> Dict[str, Any]:
    """
    Get metadata for a template without loading the full template.

    Args:
        template_name: Name of the template file

    Returns:
        Dictionary containing template metadata

    Raises:
        FileNotFoundError: If template file doesn't exist
    """
    template_data = load_template(template_name)
    return template_data.get('metadata', {})


def get_template_variables(template_name: str) -> List[str]:
    """
    Extract all variables used in a template.

    Args:
        template_name: Name of the template file

    Returns:
        List of variable names used in the template

    Raises:
        FileNotFoundError: If template file doesn't exist
    """
    template_data = load_template(template_name)
    template_content = template_data.get('template', '')

    jinja_template = _get_jinja_env().parse(template_content)
    variables = meta.find_undeclared_variables(jinja_template)

    return list(variables)


def _validate_template_structure(template_data: Dict[str, Any], template_name: str) -> None:
    """
    Validate that the template has the required structure.

    Args:
        template_data: The loaded template data
        template_name: Name of the template (for error messages)

    Raises:
        ValueError: If template structure is invalid
    """
    required_sections = ['metadata', 'template', 'response_format']

    for section in required_sections:
        if section not in template_data:
            raise ValueError(f"Template {template_name} missing required section: {section}")

    # Validate metadata
    metadata = template_data['metadata']
    required_metadata_fields = ['name', 'version', 'description', 'type']

    for field in required_metadata_fields:
        if field not in metadata:
            raise ValueError(f"Template {template_name} missing required metadata field: {field}")

    # Validate version format (semantic versioning)
    version = metadata['version']
    import re
    if not re.match(r'^\d+\.\d+\.\d+$', version):
        raise ValueError(f"Template {template_name} version {version} doesn't follow semantic versioning")


def clear_cache() -> None:
    """Clear the template cache."""
    global _template_cache
    _template_cache.clear()