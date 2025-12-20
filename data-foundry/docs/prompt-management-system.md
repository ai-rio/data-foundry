# Data Foundry Prompt Management System

## Overview

The Data Foundry Prompt Management System is a comprehensive solution for managing AI prompts used throughout the platform. It provides a centralized approach to prompt operations (PromptOps) with externalized prompt management, versioning, validation, and multi-provider AI integration through LiteLLM.

### Key Features

- **System Prompts**: Pre-defined expert prompts for specialized AI roles
- **Template Management**: YAML-based user prompts with Jinja2 templating
- **Validation**: Comprehensive prompt syntax and response format validation
- **Caching**: Performance optimization through intelligent caching
- **Versioning**: Semantic versioning for prompts and templates
- **Multi-Provider Support**: Integration with multiple AI providers via LiteLLM
- **Externalized Configuration**: Edit prompts without code deployment

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────┐
│                   Prompt Management System              │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────────────────────┐ │
│  │   System        │  │         PromptManager             │ │
│  │   Prompts       │  │                                 │ │
│  │                 │  │  ┌─────────┐  ┌─────────────────┐ │ │
│  │ • DataLabeling  │  │  │ Cache   │  │ Template Engine │ │ │
│  │ • PIIAnalyst    │  │  │ Manager │  │                 │ │ │
│  │ • Confidence    │  │  └─────────┘  │ - Jinja2        │ │ │
│  │   Assessor      │  │               │ - Validation     │ │ │
│  └─────────────────┘  │               │ - Rendering      │ │ │
│                       └─────────────────┘ └─────────────────┘ │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              Template System                             │ │
│  │                                                         │ │
│  │  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐ │ │
│  │  │ YAML Templates│  │  Validation │  │  Versioning  │ │ │
│  │  │              │  │             │  │              │ │ │
│  │  │ • Metadata   │  │ • Syntax     │  │ • Semantic   │ │ │
│  │  │ • Jinja2     │  │ • Variables  │  │   Versioning │ │ │
│  │  │ • Response   │  │ • Security   │  │ • Compatibility│ │ │
│  │  │   Format     │  │ • Consistency│  │ • Migration   │ │ │
│  │  └──────────────┘  └─────────────┘  └──────────────┘ │ │
│  └─────────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────┘
```

## Quick Start

### Basic Usage

```python
from src.core.prompts import get_prompt_manager

# Get the global prompt manager
manager = get_prompt_manager()

# Use system prompts
system_prompt = manager.get_system_prompt("data_labeling_expert")

# Load and render templates
variables = {
    "data_record": {"name": "Acme Corp", "email": "contact@acme.com"},
    "categories": ["enterprise", "prospect"],
    "context": "Lead classification"
}

rendered = manager.render_template("data_classification.yaml", variables)
```

### Direct Access to Components

```python
from src.core.prompts import (
    SystemPromptType,
    load_template,
    render_template,
    validate_template_syntax
)

# Get system prompt directly
from src.core.prompts.system import get_system_prompt
prompt = get_system_prompt(SystemPromptType.DATA_LABELING_EXPERT)

# Load template directly
template = load_template("data_classification.yaml")

# Validate template
validate_template_syntax(template["template"])
```

## System Prompts

### Available System Prompts

#### 1. DataLabelingExpert (`data_labeling_expert`)
- **Purpose**: Expert in data classification and labeling
- **Use Cases**: Categorizing data records, assigning labels, quality assessment
- **Version**: 1.0.0

```python
prompt = manager.get_system_prompt("data_labeling_expert")
```

#### 2. PIIAnalyst (`pii_analyst`)
- **Purpose**: Privacy and PII detection specialist
- **Use Cases**: Identifying sensitive information, privacy compliance
- **Version**: 1.0.0

```python
prompt = manager.get_system_prompt("pii_analyst")
```

#### 3. ConfidenceAssessor (`confidence_assessor`)
- **Purpose**: AI confidence assessment specialist
- **Use Cases**: Scoring confidence, uncertainty quantification, reliability assessment
- **Version**: 1.0.0

```python
prompt = manager.get_system_prompt("confidence_assessor")
```

## Template System

### Template Structure

Templates are defined in YAML format with the following structure:

```yaml
# Metadata section
metadata:
  name: "Template Name"
  version: "1.0.0"
  description: "Template description"
  type: "data_classification"  # data_classification, pii_detection, confidence_assessment
  author: "Data Foundry Team"
  created_at: "2024-12-20"
  required_variables:
    - data_record
    - categories
    - context
  optional_variables:
    - examples
    - rules
    - threshold

# Jinja2 template content
template: |
  Your prompt template here with {{ variables }}
  {% for item in list %}
  - {{ item }}
  {% endfor %}

# Expected response format (JSON Schema)
response_format:
  type: "object"
  properties:
    category:
      type: "string"
      description: "The selected category"
    confidence:
      type: "number"
      minimum: 0.0
      maximum: 1.0
      description: "Confidence score"
    reasoning:
      type: "string"
      description: "Explanation for the decision"
  required:
    - category
    - confidence
    - reasoning
```

### Jinja2 Features

The template system supports all Jinja2 features:

#### Variables
```jinja2
{{ variable_name }}
```

#### Loops
```jinja2
{% for item in items %}
- {{ item.name }}
{% endfor %}
```

#### Conditionals
```jinja2
{% if condition %}
Content when condition is true
{% else %}
Content when condition is false
{% endif %}
```

#### Filters
```jinja2
{{ data | tojson(indent=2) }}
{{ text | upper }}
```

### Example: Data Classification Template

```yaml
metadata:
  name: "Data Classification Template"
  version: "1.0.0"
  type: "data_classification"
  required_variables:
    - data_record
    - categories
    - context

template: |
  Please analyze the following data record:

  Data: {{ data_record | tojson }}

  Available categories: {{ categories | join(', ') }}

  Context: {{ context }}

  Provide classification with confidence score and reasoning.

response_format:
  type: "object"
  properties:
    category:
      type: "string"
    confidence:
      type: "number"
      minimum: 0.0
      maximum: 1.0
    reasoning:
      type: "string"
    requires_review:
      type: "boolean"
  required:
    - category
    - confidence
    - reasoning
```

## PromptManager API

### Class Methods

#### Initialization
```python
manager = PromptManager(
    template_dir=Path("/path/to/templates"),  # Optional, defaults to built-in templates
    cache_enabled=True,                       # Enable/disable caching
    cache_ttl=3600.0                         # Cache TTL in seconds
)
```

#### System Prompt Methods
```python
# Get system prompt
prompt = manager.get_system_prompt("data_labeling_expert")

# List all system prompts
prompts = manager.list_system_prompts()
```

#### Template Methods
```python
# Get template
template = manager.get_template("data_classification.yaml")

# Get template metadata
metadata = manager.get_template_metadata("data_classification.yaml")

# Render template
rendered = manager.render_template("data_classification.yaml", variables)

# List all templates
templates = manager.list_templates()
```

#### Cache Management
```python
# Clear all caches
manager.clear_cache()

# Disable caching
manager = PromptManager(cache_enabled=False)
```

#### Validation
```python
# Validate template
is_valid = manager.validate_template("data_classification.yaml")
```

## Configuration

### Environment Variables

Add to your `.env` file:

```bash
# Prompt Management Configuration
PROMPT_TEMPLATE_DIR=src/core/prompts/templates
PROMPT_CACHE_ENABLED=true
PROMPT_CACHE_TTL=3600
PROMPT_VERSION_CHECK=true
PROMPT_VALIDATION_ENABLED=true
PROMPT_DEBUG_MODE=false

# Prompt Optimization
PROMPT_MAX_LENGTH=32000
PROMPT_TRUNCATE_ENABLED=false
PROMPT_COST_TRACKING=true
```

### Programmatic Configuration

```python
from src.core.config import Settings

settings = Settings(
    PROMPT_CACHE_ENABLED=False,
    PROMPT_CACHE_TTL=7200,
    PROMPT_DEBUG_MODE=True
)
```

## Validation

### Template Validation

The system provides comprehensive validation:

#### Syntax Validation
- Jinja2 template syntax checking
- YAML structure validation
- JSON schema validation for response formats

#### Variable Validation
- Required variable presence checking
- Type validation
- Security checks for injection prevention

#### Consistency Checks
- Metadata vs template consistency
- Version compatibility
- Security vulnerability scanning

### Example Validation
```python
from src.core.prompts.validation import (
    validate_template_syntax,
    validate_template_variables,
    validate_response_format_schema
)

# Validate template syntax
validate_template_syntax(template_content)

# Validate required variables
validate_template_variables(
    template_content,
    provided_variables,
    required_variables
)

# Validate response format
validate_response_format_schema(response_format)
```

## Performance Optimization

### Caching Strategy

The system implements multi-level caching:

1. **System Prompt Cache**: In-memory cache for system prompts
2. **Template Cache**: Cached parsed templates with TTL
3. **Rendered Prompt Cache**: Optional caching of rendered prompts

### Cache Configuration

```python
# Configure cache TTL and size
manager = PromptManager(
    cache_enabled=True,
    cache_ttl=3600  # 1 hour
)

# Clear expired entries
manager.clear_cache()
```

### Performance Tips

1. **Enable caching** for production environments
2. **Set appropriate TTL** based on template update frequency
3. **Use singleton pattern** via `get_prompt_manager()`
4. **Pre-load frequently used templates**
5. **Monitor cache hit rates**

## Security Considerations

### Template Security

The system implements several security measures:

1. **Variable Sanitization**: Prevents code injection
2. **Jinja2 Sandboxing**: Restricted template execution
3. **Input Validation**: Validates all template variables
4. **Consistency Checks**: Detects potential security issues

### Best Practices

1. **Validate all user inputs** before template rendering
2. **Use allowlists** for template variables
3. **Regular security audits** of templates
4. **Limit template complexity** to prevent DoS
5. **Monitor for unusual template usage**

## Versioning and Migration

### Semantic Versioning

Templates and prompts use semantic versioning (MAJOR.MINOR.PATCH):

- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes

### Version Management

```python
# Check template version
metadata = manager.get_template_metadata("template.yaml")
version = metadata["version"]

# Validate version compatibility
try:
    manager._check_template_version("template.yaml", "1.0.0")
except PromptVersionError as e:
    print(f"Version mismatch: {e}")
```

### Migration Guide

When updating templates:

1. **Update minor version** for backward-compatible changes
2. **Update major version** for breaking changes
3. **Document all changes**
4. **Provide migration path**
5. **Test compatibility**

## Integration with AI Providers

### LiteLLM Integration

The prompt management system integrates seamlessly with LiteLLM:

```python
from litellm import completion

# Get system and user prompts
system_prompt = manager.get_system_prompt("data_labeling_expert")
user_prompt = manager.render_template("data_classification.yaml", variables)

# Make AI request
response = completion(
    model="gpt-4",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ],
    response_format={
        "type": "json_object"
    }
)
```

### Multi-Provider Support

The system works with any LiteLLM-supported provider:

```python
providers = [
    "gpt-4",           # OpenAI
    "claude-3-opus",   # Anthropic
    "command-r+",      # Cohere
    "gemini-pro"       # Google
]

for model in providers:
    response = completion(
        model=model,
        messages=[...],
        # System will handle provider-specific formatting
    )
```

## Monitoring and Debugging

### Debug Mode

Enable debug mode for detailed logging:

```python
from src.core.config import Settings

settings = Settings(PROMPT_DEBUG_MODE=True)
```

### Monitoring Metrics

Track:
- Cache hit rates
- Template load times
- Render performance
- Error rates
- Provider response times

### Logging

The system provides comprehensive logging:

```python
import logging

# Enable prompt management logging
logging.getLogger("src.core.prompts").setLevel(logging.DEBUG)
```

## Best Practices

### Template Design

1. **Keep templates focused** on single tasks
2. **Use clear variable names**
3. **Provide examples** in templates
4. **Include validation rules**
5. **Document all variables**

### Prompt Engineering

1. **Combine system and user prompts** effectively
2. **Use chain-of-thought** prompting
3. **Provide clear instructions**
4. **Include output format examples**
5. **Test with various inputs**

### Performance

1. **Enable caching** in production
2. **Monitor prompt lengths**
3. **Optimize templates** for speed
4. **Use async rendering** when possible
5. **Implement rate limiting**

## Troubleshooting

### Common Issues

#### Template Not Found
```
PromptManagerError: Template not found: template.yaml
```
- Check template directory
- Verify file extension (.yaml or .yml)
- Ensure correct file permissions

#### Variable Missing
```
PromptManagerError: Missing required template variables: data_record
```
- Check required_variables in metadata
- Verify variable names in template
- Ensure all required variables are provided

#### Invalid Template Syntax
```
PromptManagerError: Invalid Jinja2 template syntax
```
- Check Jinja2 syntax
- Verify bracket matching
- Validate filter usage

#### Cache Issues
- Clear cache: `manager.clear_cache()`
- Check TTL settings
- Verify cache configuration

### Debug Steps

1. **Enable debug mode**
2. **Check logs** for errors
3. **Validate template** manually
4. **Test with simple data**
5. **Check configuration**

## API Reference

### PromptManager Class

```python
class PromptManager:
    def __init__(
        self,
        template_dir: Optional[Path] = None,
        cache_enabled: bool = True,
        cache_ttl: float = 3600.0,
        skip_singleton: bool = False
    ):
        """Initialize PromptManager"""

    def get_system_prompt(self, prompt_type: str) -> str:
        """Get a system prompt by type"""

    def get_template(self, template_name: str) -> Dict[str, Any]:
        """Get a template by name"""

    def render_template(
        self,
        template_name: str,
        variables: Dict[str, Any]
    ) -> str:
        """Render a template with variables"""

    def get_template_metadata(self, template_name: str) -> Dict[str, Any]:
        """Get template metadata"""

    def list_templates(self) -> List[str]:
        """List all available templates"""

    def list_system_prompts(self) -> List[str]:
        """List all system prompt types"""

    def clear_cache(self) -> None:
        """Clear all caches"""

    def validate_template(self, template_name: str) -> bool:
        """Validate a template"""
```

### Exception Classes

```python
class PromptManagerError(Exception):
    """Base exception for PromptManager errors"""

class PromptVersionError(PromptManagerError):
    """Exception for version compatibility issues"""
```

### Global Functions

```python
def get_prompt_manager() -> PromptManager:
    """Get the global PromptManager instance"""

def reset_prompt_manager() -> None:
    """Reset the global PromptManager instance"""
```

## Contributing

### Adding New System Prompts

1. Create prompt class in `src/core/prompts/system.py`
2. Add to SystemPromptType enum
3. Update system prompt registry
4. Write tests
5. Update documentation

### Creating New Templates

1. Create YAML file in `templates/` directory
2. Follow template structure
3. Include metadata
4. Test validation
5. Add examples

### Extending Validation

1. Add validators to `src/core/prompts/validation.py`
2. Update PromptManager
3. Write tests
4. Document changes

## License

This Prompt Management System is part of Data Foundry and follows the same license terms.

## Support

For support and questions:
- Create an issue in the repository
- Check the documentation
- Review test cases for examples