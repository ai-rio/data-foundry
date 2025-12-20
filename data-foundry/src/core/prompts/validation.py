"""
Prompt Template Validation

This module provides validation functions for prompt templates,
including Jinja2 syntax validation, variable validation, and response format validation.
"""

import re
from typing import List, Dict, Any, Set, Optional
import json
import jsonschema
from jinja2 import Environment, TemplateSyntaxError, meta


def validate_template_syntax(template_content: str) -> None:
    """
    Validate that a template has valid Jinja2 syntax.

    Args:
        template_content: The template content to validate

    Raises:
        ValueError: If template has invalid Jinja2 syntax
    """
    try:
        env = Environment()
        env.parse(template_content)
    except TemplateSyntaxError as e:
        raise ValueError(f"Invalid Jinja2 template syntax: {e.message} at line {e.lineno}")


def validate_template_variables(
    template_content: str,
    provided_variables: Dict[str, Any],
    required_variables: Optional[List[str]] = None
) -> None:
    """
    Validate that all required template variables are provided.

    Args:
        template_content: The template content to analyze
        provided_variables: Dictionary of variables that will be provided
        required_variables: List of variables that must be provided (from metadata)

    Raises:
        ValueError: If required variables are missing
    """
    # Extract variables from template
    env = Environment()
    parsed_template = env.parse(template_content)
    template_variables = meta.find_undeclared_variables(parsed_template)

    # Check required variables from metadata
    if required_variables:
        missing_required = set(required_variables) - set(provided_variables.keys())
        if missing_required:
            raise ValueError(
                f"Missing required template variables: {', '.join(missing_required)}"
            )

    # Check variables used in template but not provided
    # (excluding variables that might be provided by Jinja2 built-ins and those used in {% if %} blocks)
    jinja_builtins = {'range', 'loop', 'super', 'self', 'varargs', 'kwargs', 'caller'}
    used_variables = template_variables - jinja_builtins

    # Allow optional variables (those not explicitly required) to be missing
    # Only check if required variables are missing (already done above)
    if required_variables:
        # Only complain about missing variables that are explicitly used (not in conditionals)
        used_mandatory = set(required_variables)
        missing_provided = used_mandatory - set(provided_variables.keys())
        if missing_provided:
            raise ValueError(
                f"Template uses required variables that are not provided: {', '.join(missing_provided)}"
            )


def validate_response_format_schema(response_format: Dict[str, Any]) -> None:
    """
    Validate that a response format is a valid JSON schema.

    Args:
        response_format: The response format specification

    Raises:
        ValueError: If response format is invalid
    """
    try:
        # Validate that it's a valid JSON schema
        jsonschema.Draft7Validator.check_schema(response_format)
    except jsonschema.SchemaError as e:
        raise ValueError(f"Invalid response format schema: {e.message}")

    # Check for required properties in the schema
    if response_format.get('type') != 'object':
        raise ValueError("Response format must be of type 'object'")

    if 'properties' not in response_format:
        raise ValueError("Response format must specify 'properties'")

    if 'required' not in response_format:
        raise ValueError("Response format must specify 'required' fields")


def validate_semantic_version(version: str) -> bool:
    """
    Validate that a version string follows semantic versioning.

    Args:
        version: Version string to validate

    Returns:
        True if valid semantic version, False otherwise
    """
    pattern = r'^\d+\.\d+\.\d+(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?(\+[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$'
    return bool(re.match(pattern, version))


def validate_template_name(template_name: str) -> bool:
    """
    Validate that a template name is valid.

    Args:
        template_name: Template name to validate

    Returns:
        True if valid template name, False otherwise
    """
    # Template names should be alphanumeric with underscores and hyphens
    pattern = r'^[a-zA-Z0-9_-]+\.yaml$'
    return bool(re.match(pattern, template_name))


def validate_metadata_structure(metadata: Dict[str, Any]) -> None:
    """
    Validate that template metadata has the required structure.

    Args:
        metadata: Template metadata dictionary

    Raises:
        ValueError: If metadata structure is invalid
    """
    required_fields = ['name', 'version', 'description', 'type', 'author', 'created_at']

    for field in required_fields:
        if field not in metadata:
            raise ValueError(f"Metadata missing required field: {field}")

    # Validate version format
    if not validate_semantic_version(metadata['version']):
        raise ValueError(
            f"Version {metadata['version']} doesn't follow semantic versioning"
        )

    # Validate type is one of the allowed types
    allowed_types = ['data_classification', 'pii_detection', 'confidence_assessment']
    if metadata['type'] not in allowed_types:
        raise ValueError(
            f"Template type {metadata['type']} not in allowed types: {allowed_types}"
        )

    # Validate required_variables is a list if present
    if 'required_variables' in metadata:
        if not isinstance(metadata['required_variables'], list):
            raise ValueError("required_variables must be a list")

        # Check that all required variables are strings
        for var in metadata['required_variables']:
            if not isinstance(var, str):
                raise ValueError("All required_variables must be strings")


def validate_jinja2_filter_usage(template_content: str) -> List[str]:
    """
    Check for usage of custom Jinja2 filters that might not be available.

    Args:
        template_content: The template content to check

    Returns:
        List of custom filters that might need to be defined
    """
    # Extract filter usage from template
    filter_pattern = r'\|\s*([a-zA-Z_][a-zA-Z0-9_]*)'
    matches = re.findall(filter_pattern, template_content)

    # List of standard Jinja2 filters
    standard_filters = {
        'abs', 'attr', 'batch', 'capitalize', 'center', 'count', 'd',
        'default', 'dictsort', 'e', 'escape', 'filesizeformat',
        'first', 'float', 'forceescape', 'format', 'groupby', 'indent',
        'int', 'join', 'last', 'length', 'list', 'lower', 'map',
        'max', 'min', 'pprint', 'random', 'reject', 'rejectattr',
        'replace', 'reverse', 'round', 'safe', 'select', 'selectattr',
        'slice', 'sort', 'string', 'striptags', 'sum', 'title',
        'tojson', 'trim', 'truncate', 'unique', 'upper', 'urlencode',
        'urlize', 'wordcount', 'wordwrap', 'xmlattr'
    }

    custom_filters = set(matches) - standard_filters
    return list(custom_filters)


def validate_template_consistency(template_data: Dict[str, Any]) -> List[str]:
    """
    Validate that all parts of the template are consistent with each other.

    Args:
        template_data: Complete template data including metadata and content

    Returns:
        List of warning messages about potential issues
    """
    warnings = []

    metadata = template_data.get('metadata', {})
    template_content = template_data.get('template', '')
    response_format = template_data.get('response_format', {})

    # Check if required_variables in metadata match variables in template
    required_vars = set(metadata.get('required_variables', []))
    env = Environment()
    parsed_template = env.parse(template_content)
    template_vars = meta.find_undeclared_variables(parsed_template)

    # Warn if template uses variables not listed as required
    jinja_builtins = {'range', 'loop', 'super', 'self', 'varargs', 'kwargs', 'caller'}
    used_vars = template_vars - jinja_builtins
    missing_in_required = used_vars - required_vars

    if missing_in_required:
        warnings.append(
            f"Template uses variables not listed in required_variables: {', '.join(missing_in_required)}"
        )

    # Warn if required_variables has variables not used in template
    unused_required = required_vars - used_vars
    if unused_required:
        warnings.append(
            f"required_variables has entries not used in template: {', '.join(unused_required)}"
        )

    # Check for potential security issues in template
    dangerous_patterns = [
        (r'\{\{\s*config\s*\}\}', 'Using config object in template'),
        (r'\{\{\s*\.+.*\}\}', 'Using attribute access that might be unsafe'),
        (r'\{\%\s*include\s+', 'Using include directive'),
        (r'\{\%\s*import\s+', 'Using import directive'),
    ]

    for pattern, message in dangerous_patterns:
        if re.search(pattern, template_content):
            warnings.append(f"Potential security issue: {message}")

    # Validate response format
    try:
        validate_response_format_schema(response_format)
    except ValueError as e:
        warnings.append(f"Invalid response format: {e}")

    return warnings


def sanitize_template_variables(variables: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize template variables to prevent injection attacks.

    Args:
        variables: Dictionary of variables to sanitize

    Returns:
        Sanitized variables dictionary
    """
    sanitized = {}

    for key, value in variables.items():
        # Convert complex objects to JSON to prevent code execution
        if isinstance(value, (dict, list)):
            sanitized[key] = json.dumps(value, ensure_ascii=False)
        elif callable(value):
            # Don't allow callable objects
            raise ValueError(f"Template variable '{key}' cannot be callable")
        elif hasattr(value, '__call__'):
            # Don't allow objects with __call__ method
            raise ValueError(f"Template variable '{key}' cannot be callable object")
        else:
            sanitized[key] = value

    return sanitized