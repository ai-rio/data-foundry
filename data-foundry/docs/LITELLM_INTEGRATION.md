# LiteLLM Integration for Data Foundry

This document provides a comprehensive overview of the LiteLLM integration that enables unified access to multiple AI providers with intelligent fallbacks, cost tracking, and performance optimization.

## Overview

The LiteLLM integration consists of:

1. **LiteLLM Service** (`src/services/litellm_service.py`) - Direct LiteLLM API integration
2. **Updated AI Service** (`src/services/ai_service.py`) - High-level service using LiteLLM
3. **Comprehensive Test Suite** - Unit, integration, and performance tests
4. **Environment Configuration** - Updated settings and API keys

## Architecture

```
┌─────────────────┐
│   AI Service    │  ← High-level interface
└────────┬────────┘
         │
┌────────▼────────┐
│ LiteLLM Service │  ← Direct LiteLLM integration
└────────┬────────┘
         │
┌────────▼────────┐
│  LiteLLM Lib    │  ← Unified provider access
└────────┬────────┘
         │
    ┌────▼─────┐
    │Providers │
    │- OpenAI  │
    │- Anthropic│
    │- Azure   │
    │- Google  │
    │- etc.    │
    └──────────┘
```

## Key Features

### 1. Multi-Provider Support
- **OpenAI**: GPT-4, GPT-3.5-Turbo, etc.
- **Anthropic**: Claude-3 family
- **Azure OpenAI**: Custom deployments
- **Google**: Gemini models
- **And more**: 100+ providers supported

### 2. Intelligent Fallback
- Primary model failure → Automatic fallback
- Configurable fallback chain
- Retry logic with exponential backoff
- Provider-specific error handling

### 3. Cost Tracking
- Per-token cost calculation
- Multi-currency support
- Tiered pricing based on volume
- Real-time cost estimation
- Stripe billing integration

### 4. Performance Optimization
- Response caching in Redis
- Rate limiting per tenant
- Concurrent request handling
- Streaming support
- Performance monitoring

### 5. Comprehensive Logging
- Audit trail for all operations
- Usage tracking per tenant
- Error logging with context
- Performance metrics

## Configuration

### Environment Variables

```bash
# AI Provider API Keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=ant-...
AZURE_API_KEY=...
AZURE_API_BASE=...
AZURE_API_VERSION=...
GOOGLE_API_KEY=...

# LiteLLM Settings
LITELLM_LOGGING=true
LITELLM_CACHE_TTL=3600
LITELLM_REQUEST_TIMEOUT=30

# Model Configuration
PRIMARY_MODEL=gpt-4o
FALLBACK_MODELS=claude-3-5-sonnet,gpt-4o-mini
MODEL_LIST=gpt-4o,claude-3-5-sonnet,gpt-4o-mini,gpt-3.5-turbo

# Cost Tracking
ENABLE_COST_TRACKING=true
COST_TRACKING_CURRENCY=USD
BILLING_PRECISION=6
```

### Model Configuration

```python
# In src/core/config.py
PRIMARY_MODEL = "gpt-4o"
FALLBACK_MODELS = ["claude-3-5-sonnet", "gpt-4o-mini"]
MODEL_LIST = [
    "gpt-4o",
    "claude-3-5-sonnet",
    "gpt-4o-mini",
    "gpt-3.5-turbo"
]
```

## Usage Examples

### Basic Completion

```python
from src.services.ai_service import AIService, AIRequest

service = AIService()
await service.initialize()

request = AIRequest(
    prompt="Analyze this customer data for value categorization",
    system_prompt="You are a data analysis expert.",
    temperature=0.3,
    max_tokens=200,
    tenant_id="tenant_123"
)

response = await service.completion(request)
print(f"Category: {response.content}")
print(f"Model: {response.model}")
print(f"Cost: ${response.cost}")
print(f"Tokens: {response.usage.total_tokens}")
```

### With Prompt Template

```python
request = AIRequest(
    prompt_template="data_categorization",
    template_vars={
        "company_name": "Acme Corp",
        "email_domain": "acme.com"
    },
    response_format="json",
    tenant_id="tenant_123"
)

response = await service.completion(request)
result = json.loads(response.content)
```

### Batch Processing

```python
requests = [
    AIRequest(prompt=f"Analyze record {i}", tenant_id="batch")
    for i in range(100)
]

responses = await service.batch_completion(
    requests,
    max_concurrent=5
)
```

### Streaming

```python
async for chunk in service.stream_completion(
    prompt="Generate a long response",
    tenant_id="streaming"
):
    print(chunk, end="")
```

## Testing

### Run Unit Tests
```bash
python run_litellm_tests.py --type unit
```

### Run Integration Tests (requires API keys)
```bash
# Set your API keys first
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=ant-...

python run_litellm_tests.py --type integration
```

### Run Performance Tests
```bash
python run_litellm_tests.py --type performance
```

### Run All Tests
```bash
python run_litellm_tests.py --type all
```

## Monitoring and Metrics

### Service Metrics
```python
# Get performance metrics
metrics = await ai_service.get_service_metrics()
print(f"Requests: {metrics['requests_total']}")
print(f"Success Rate: {metrics['requests_success'] / metrics['requests_total'] * 100:.1f}%")
print(f"Avg Response Time: {metrics['avg_response_time']:.2f}ms")
print(f"Cache Hit Rate: {metrics['cache_hits'] / (metrics['cache_hits'] + metrics['cache_misses']) * 100:.1f}%")
```

### Health Check
```python
health = await ai_service.health_check()
print(f"Service Healthy: {health['litellm_service']['healthy']}")

for model, status in health['litellm_service']['models'].items():
    print(f"{model}: {status['status']}")
```

## Error Handling

### Custom Exceptions
```python
from src.services.litellm_service import LiteLLMError

try:
    response = await service.completion(request)
except LiteLLMError as e:
    print(f"Provider: {e.provider}")
    print(f"Model: {e.model}")
    print(f"Error Type: {e.error_type}")
    print(f"Retryable: {e.retryable}")
```

### Error Types
- `rate_limit_error` - Retry with backoff
- `timeout_error` - Retry
- `connection_error` - Retry
- `server_error` - Retry
- `authentication_error` - Don't retry (fix config)
- `invalid_request` - Don't retry (fix request)

## Cost Management

### Pricing Configuration
```python
# In src/services/cost_service.py
self._model_pricing.update({
    "gpt-4o": ModelPricing(
        provider=AIProvider.OPENAI,
        model="gpt-4o",
        input_token_cost=Decimal("0.005"),  # $0.005 per 1K
        output_token_cost=Decimal("0.015"), # $0.015 per 1K
        context_window=128000
    )
})
```

### Cost Tracking
```python
# Track cost per tenant
cost_service = CostService()
cost_data = await cost_service.get_usage_report(
    tenant_id="tenant_123",
    start_date=datetime.now() - timedelta(days=30),
    end_date=datetime.now()
)

print(f"Monthly Cost: ${cost_data['usage']['monthly_cost']}")
print(f"Monthly Tokens: {cost_data['usage']['monthly_tokens']}")
```

## Deployment Considerations

### 1. Security
- Secure API key storage (environment variables, secrets manager)
- Request validation and sanitization
- Rate limiting per tenant
- Audit logging

### 2. Performance
- Redis clustering for cache scaling
- Connection pooling for databases
- Async/await throughout
- Monitor response times

### 3. Reliability
- Circuit breakers for failing providers
- Health checks and monitoring
- Graceful degradation
- Backup strategies

### 4. Cost Control
- Daily/monthly cost limits
- Usage alerts
- Tiered pricing for different tenants
- Cost optimization recommendations

## Troubleshooting

### Common Issues

1. **API Authentication Errors**
   - Check API keys are correctly set
   - Verify keys have necessary permissions
   - Check billing status with providers

2. **Rate Limiting**
   - Implement proper backoff
   - Consider increasing rate limits
   - Use multiple provider keys

3. **Slow Response Times**
   - Enable caching
   - Optimize prompt size
   - Check network latency
   - Consider regional deployments

4. **High Costs**
   - Monitor token usage
   - Optimize prompts
   - Use cheaper models where appropriate
   - Set cost alerts

### Debug Logging
```python
import logging
logging.getLogger("src.services.litellm_service").setLevel(logging.DEBUG)
```

## Migration from Direct OpenAI

The LiteLLM integration is backward compatible. Existing code using the AI Service will continue to work without changes.

### Before
```python
# Direct OpenAI integration (old)
from openai import OpenAI
client = OpenAI(api_key=...)
response = client.chat.completions.create(...)
```

### After
```python
# Unified AI Service (new)
from src.services.ai_service import AIService, AIRequest
service = AIService()
request = AIRequest(prompt="...")
response = await service.completion(request)
```

## Future Enhancements

1. **Model Routing**
   - Intelligent model selection based on task
   - A/B testing for models
   - Custom routing rules

2. **Fine-tuning Support**
   - Model fine-tuning integration
   - Custom model deployment
   - Performance comparison

3. **Advanced Features**
   - Function calling/tool use
   - Image generation
   - Audio transcription
   - Vector search integration

## Support

For issues or questions:
1. Check the test suite for examples
2. Review logs for error details
3. Consult LiteLLM documentation
4. Check provider API documentation
5. Create an issue with detailed reproduction steps