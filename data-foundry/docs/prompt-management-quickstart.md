# Prompt Management System - Quick Start Guide

## 5-Minute Quick Start

### 1. Basic Usage

```python
from src.core.prompts import get_prompt_manager

# Initialize the prompt manager
manager = get_prompt_manager()

# Use a system prompt
system_prompt = manager.get_system_prompt("data_labeling_expert")
print(f"System prompt: {system_prompt[:100]}...")

# Render a template
variables = {
    "data_record": {"name": "Acme Corp", "revenue": "5M"},
    "categories": ["enterprise", "high_value"],
    "context": "Company evaluation"
}
user_prompt = manager.render_template("data_classification.yaml", variables)
print(f"User prompt: {user_prompt[:100]}...")
```

### 2. Available System Prompts

- `data_labeling_expert` - For data classification tasks
- `pii_analyst` - For PII detection and privacy analysis
- `confidence_assessor` - For confidence scoring

### 3. Template Example

```yaml
# my_template.yaml
metadata:
  name: "My Template"
  version: "1.0.0"
  type: "data_classification"
  required_variables:
    - data_record
    - categories

template: |
  Analyze this data: {{ data_record | tojson }}
  Categories: {{ categories | join(', ') }}

response_format:
  type: "object"
  properties:
    category: {type: "string"}
    confidence: {type: "number"}
  required: [category, confidence]
```

### 4. Configuration

Add to `.env`:
```bash
PROMPT_CACHE_ENABLED=true
PROMPT_CACHE_TTL=3600
PROMPT_VALIDATION_ENABLED=true
```

## Common Patterns

### Pattern 1: Classification Task
```python
# Get system prompt for classification
system_prompt = manager.get_system_prompt("data_labeling_expert")

# Prepare data
data = {"text": "User feedback about our product", "rating": 5}
categories = ["positive", "negative", "neutral"]

# Render user prompt
user_prompt = manager.render_template("data_classification.yaml", {
    "data_record": data,
    "categories": categories,
    "context": "Sentiment analysis"
})

# Use with LiteLLM
from litellm import completion
response = completion(
    model="gpt-4",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
)
```

### Pattern 2: PII Detection
```python
# Use PII analyst system prompt
system_prompt = manager.get_system_prompt("pii_analyst")

# Check text for PII
user_prompt = f"""
Please analyze this text for PII:
"{user_text}"

Identify any personal information and suggest actions.
"""

response = completion(
    model="gpt-4",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
)
```

### Pattern 3: Confidence Scoring
```python
# Get confidence assessment prompt
system_prompt = manager.get_system_prompt("confidence_assessor")

# Score prediction confidence
user_prompt = f"""
Previous prediction: {prediction}
Model output: {model_output}
Data context: {context}

Assess confidence in this prediction.
"""

response = completion(
    model="gpt-4",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
)
```

## Best Practices

1. **Always combine system and user prompts**
2. **Validate template variables before rendering**
3. **Enable caching for production**
4. **Monitor prompt performance**
5. **Version your templates**

## Next Steps

- Read the [full documentation](prompt-management-system.md)
- Check [integration tests](../tests/integration/test_prompt_management_system.py)
- Create your own templates
- Contribute new prompts