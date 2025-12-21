"""
Minimal TRUE Integration Test for Real OpenRouter API

This is a simplified test to validate real API integration works.
Following TDD methodology: RED (failing) → GREEN (minimal implementation) → REFACTOR
"""

import asyncio
import json
import os
import pytest
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

# Load environment with real OpenRouter API key
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env.local", override=True)

# Verify we have the real API key
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    pytest.skip("OPENROUTER_API_KEY not found - cannot run real API tests")

print(f"✅ Found OpenRouter API key: {OPENROUTER_API_KEY[:20]}...")


@pytest.mark.asyncio
class TestRealAPIMinimal:
    """Minimal test for real OpenRouter API integration."""

    async def test_direct_openrouter_api_call(self):
        """
        RED PHASE: Test direct OpenRouter API call.
        This should fail initially, then pass after GREEN phase implementation.
        """
        try:
            # Import LiteLLM for real API call
            import litellm
            from litellm import acompletion

            # Configure LiteLLM with real OpenRouter API key
            litellm.openrouter_api_key = OPENROUTER_API_KEY
            litellm.set_verbose = True

            # Test model that should work with OpenRouter
            model = "openrouter/openai/gpt-4o-mini"

            # Make REAL API call
            start_time = time.time()

            response = await acompletion(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a data categorization assistant. Respond with JSON only."},
                    {"role": "user", "content": "Categorize this contact: John Doe, john@example.com, CEO at Tech Corp"}
                ],
                max_tokens=100,
                temperature=0.3
            )

            response_time = time.time() - start_time

            # Validate real API response
            assert response is not None, "Real API should return response"
            assert response.choices is not None, "Real API should return choices"
            assert len(response.choices) > 0, "Real API should return at least one choice"
            assert response.choices[0].message is not None, "Real API should return message"
            assert response.choices[0].message.content is not None, "Real API should return content"
            assert response.model is not None, "Real API should return model info"
            assert response.usage is not None, "Real API should return usage info"
            assert response.usage.total_tokens > 0, "Real API should use tokens"
            assert response_time < 10.0, f"Real API response should be <10s, took {response_time}s"

            # Parse and validate AI response
            content = response.choices[0].message.content.strip()
            print(f"✅ Real OpenRouter API Response: {content}")

            # Try to parse as JSON (AI should return categorization)
            try:
                result = json.loads(content)
                assert isinstance(result, dict), "AI should return JSON object"
                # Any category is fine, just validate structure
                print(f"✅ AI categorization result: {result}")
            except json.JSONDecodeError:
                # If not JSON, at least validate it's text
                assert isinstance(content, str), "Response should be text"
                assert len(content) > 0, "Response should not be empty"
                print(f"✅ AI response (text): {content}")

            # Print API details for verification
            print(f"✅ Real API Call Details:")
            print(f"   Model: {response.model}")
            print(f"   Tokens: {response.usage.total_tokens}")
            print(f"   Response time: {response_time:.2f}s")
            print(f"   Content type: {type(content)}")

        except Exception as e:
            pytest.fail(f"Real OpenRouter API call failed: {str(e)}")

    async def test_openrouter_cost_tracking(self):
        """
        RED PHASE: Test that we can track costs from real OpenRouter API.
        """
        try:
            import litellm
            from litellm import acompletion, completion_cost

            # Configure with real API key
            litellm.openrouter_api_key = OPENROUTER_API_KEY

            # Make API call
            response = await acompletion(
                model="openrouter/openai/gpt-4o-mini",
                messages=[
                    {"role": "user", "content": "Simple test for cost tracking"}
                ],
                max_tokens=50
            )

            # Calculate cost using the standard LiteLLM format
            cost = completion_cost(
                model=response.model,
                messages=[{"role": "user", "content": "Simple test for cost tracking"}]
            )

            # Validate cost calculation
            assert cost is not None, "Cost should be calculated"
            assert isinstance(cost, (float, Decimal)), "Cost should be numeric"
            assert cost >= 0, "Cost should be non-negative"

            print(f"✅ Cost tracking validated:")
            print(f"   Model: {response.model}")
            print(f"   Prompt tokens: {response.usage.prompt_tokens}")
            print(f"   Completion tokens: {response.usage.completion_tokens}")
            print(f"   Cost: ${cost}")

        except Exception as e:
            pytest.fail(f"OpenRouter cost tracking failed: {str(e)}")

    async def test_environment_configuration(self):
        """
        RED PHASE: Test that environment is properly configured for real API calls.
        """
        # Verify critical environment variables
        assert OPENROUTER_API_KEY is not None, "OPENROUTER_API_KEY must be set"
        assert len(OPENROUTER_API_KEY) > 20, "OPENROUTER_API_KEY seems too short"

        # Verify Redis is available (for caching tests)
        try:
            import redis
            r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
            r.ping()
            print("✅ Redis is available for caching tests")
        except Exception as e:
            print(f"⚠️  Redis not available: {str(e)}")

        # Verify LiteLLM is installed
        try:
            import litellm
            print(f"✅ LiteLLM imported successfully")
        except ImportError:
            pytest.fail("LiteLLM not installed")

        # Print configuration summary
        print(f"✅ Environment Configuration Summary:")
        print(f"   OpenRouter API Key: {'✓' if OPENROUTER_API_KEY else '✗'}")
        print(f"   API Key length: {len(OPENROUTER_API_KEY) if OPENROUTER_API_KEY else 0}")
        print(f"   Test model: openrouter/meta-llama/llama-3.1-8b-instruct:free")
        print(f"   Working directory: {Path.cwd()}")
        print(f"   .env.local exists: {Path('.env.local').exists()}")