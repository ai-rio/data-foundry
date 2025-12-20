"""
Unit tests for cache utilities with mocked Redis.

Tests cover:
- Cache key generation
- Serialization/deserialization
- TTL management
- Error handling
- Cache decorators
"""

import json
import time
import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Any, Dict, Optional

from src.core.cache import (
    CacheKeyGenerator,
    CacheSerializer,
    CacheDecorator,
    CacheError,
    CacheKeyError,
    CacheSerializationError,
    generate_cache_key,
    cache_result,
    cached_with_ttl,
)


class TestCacheKeyGenerator:
    """Test cache key generation functionality."""

    def test_generate_key_basic(self):
        """Test basic key generation."""
        generator = CacheKeyGenerator()
        key = generator.generate_key("test", {"param1": "value1", "param2": 123})
        assert key == "test:param1=value1:param2=123"

    def test_generate_key_with_prefix(self):
        """Test key generation with prefix."""
        generator = CacheKeyGenerator(prefix="myapp")
        key = generator.generate_key("test", {"param": "value"})
        assert key == "myapp:test:param=value"

    def test_generate_key_with_special_chars(self):
        """Test key generation with special characters."""
        generator = CacheKeyGenerator()
        key = generator.generate_key("test", {"param": "value:with:colons"})
        assert key == "test:param=value_with_colons"

    def test_generate_key_with_none_value(self):
        """Test key generation with None values."""
        generator = CacheKeyGenerator()
        key = generator.generate_key("test", {"param": None})
        assert key == "test:param=None"

    def test_generate_key_empty_params(self):
        """Test key generation with empty parameters."""
        generator = CacheKeyGenerator()
        key = generator.generate_key("test", {})
        assert key == "test"

    def test_generate_prompt_cache_key(self):
        """Test specific prompt cache key format."""
        generator = CacheKeyGenerator(prefix="prompt_cache")
        key = generator.generate_key("gpt-4o", {"prompt_hash": "abc123"})
        assert key == "prompt_cache:gpt-4o:prompt_hash=abc123"

    def test_generate_key_consistency(self):
        """Test that key generation is consistent."""
        generator = CacheKeyGenerator()
        params = {"a": 1, "b": "test", "c": True}
        key1 = generator.generate_key("func", params)
        key2 = generator.generate_key("func", params)
        assert key1 == key2

    def test_generate_key_order_independence(self):
        """Test that parameter order doesn't affect key."""
        generator = CacheKeyGenerator()
        params1 = {"a": 1, "b": 2}
        params2 = {"b": 2, "a": 1}
        key1 = generator.generate_key("func", params1)
        key2 = generator.generate_key("func", params2)
        # Should be different since we don't sort by default for performance
        assert key1 != key2

    def test_generate_key_with_sorting(self):
        """Test key generation with sorted parameters."""
        generator = CacheKeyGenerator(sort_params=True)
        params1 = {"b": 2, "a": 1}
        params2 = {"a": 1, "b": 2}
        key1 = generator.generate_key("func", params1)
        key2 = generator.generate_key("func", params2)
        assert key1 == key2


class TestCacheSerializer:
    """Test cache serialization functionality."""

    def test_serialize_dict(self):
        """Test serializing a dictionary."""
        serializer = CacheSerializer()
        data = {"key": "value", "number": 42}
        serialized = serializer.serialize(data)
        assert isinstance(serialized, str)
        assert json.loads(serialized) == data

    def test_serialize_string(self):
        """Test serializing a string."""
        serializer = CacheSerializer()
        data = "test string"
        serialized = serializer.serialize(data)
        assert serialized == data

    def test_serialize_number(self):
        """Test serializing numbers."""
        serializer = CacheSerializer()
        assert serializer.serialize(42) == "42"
        assert serializer.serialize(3.14) == "3.14"

    def test_serialize_list(self):
        """Test serializing a list."""
        serializer = CacheSerializer()
        data = [1, "two", {"three": 3}]
        serialized = serializer.serialize(data)
        assert isinstance(serialized, str)
        assert json.loads(serialized) == data

    def test_deserialize_dict(self):
        """Test deserializing a dictionary."""
        serializer = CacheSerializer()
        original = {"key": "value", "number": 42}
        serialized = json.dumps(original)
        deserialized = serializer.deserialize(serialized)
        assert deserialized == original

    def test_deserialize_string(self):
        """Test deserializing a string."""
        serializer = CacheSerializer()
        data = "test string"
        assert serializer.deserialize(data) == data

    def test_deserialize_number(self):
        """Test deserializing numbers."""
        serializer = CacheSerializer()
        assert serializer.deserialize("42") == 42
        assert serializer.deserialize("3.14") == 3.14

    def test_round_trip(self):
        """Test serialize then deserialize round trip."""
        serializer = CacheSerializer()
        original_data = {
            "text": "hello",
            "count": 5,
            "nested": {"inner": True},
            "list": [1, 2, 3]
        }
        serialized = serializer.serialize(original_data)
        deserialized = serializer.deserialize(serialized)
        assert deserialized == original_data

    def test_serialize_unsupported_type(self):
        """Test serializing an unsupported type."""
        serializer = CacheSerializer()
        with pytest.raises(CacheSerializationError):
            serializer.serialize(set([1, 2, 3]))  # Sets are not JSON serializable

    def test_deserialize_invalid_json(self):
        """Test deserializing invalid JSON."""
        serializer = CacheSerializer()
        with pytest.raises(CacheSerializationError):
            serializer.deserialize("invalid json {")

    def test_deserialize_none(self):
        """Test deserializing None."""
        serializer = CacheSerializer()
        with pytest.raises(CacheSerializationError):
            serializer.deserialize(None)


class TestCacheDecorator:
    """Test cache decorator functionality."""

    @patch('src.core.cache.RedisCache')
    def test_cache_result_decorator(self, mock_redis_cache):
        """Test basic cache_result decorator."""
        # Setup mock
        mock_instance = Mock()
        mock_instance.get.return_value = None
        mock_instance.set.return_value = True
        mock_redis_cache.return_value = mock_instance

        # Define function with decorator
        @cache_result(key_prefix="test", ttl=300)
        def expensive_function(x: int, y: int) -> int:
            return x * y

        # Call function
        result = expensive_function(3, 4)

        # Verify result and cache calls
        assert result == 12
        mock_instance.get.assert_called_once()
        mock_instance.set.assert_called_once()

    @patch('src.core.cache.RedisCache')
    def test_cache_result_with_hit(self, mock_redis_cache):
        """Test cache_result decorator with cache hit."""
        # Setup mock
        mock_instance = Mock()
        mock_instance.get.return_value = "12"  # Cached result as string
        mock_instance.set.return_value = True
        mock_redis_cache.return_value = mock_instance

        @cache_result(key_prefix="test", ttl=300)
        def expensive_function(x: int, y: int) -> int:
            return x * y

        # Call function
        result = expensive_function(3, 4)

        # Verify cached result was returned
        assert result == 12
        mock_instance.get.assert_called_once()
        mock_instance.set.assert_not_called()  # Not called on cache hit

    @patch('src.core.cache.RedisCache')
    def test_cache_result_with_args_kwargs(self, mock_redis_cache):
        """Test cache_result decorator with both args and kwargs."""
        mock_instance = Mock()
        mock_instance.get.return_value = None
        mock_instance.set.return_value = True
        mock_redis_cache.return_value = mock_instance

        @cache_result(key_prefix="test", ttl=300)
        def complex_function(a, b, c=None, d=None):
            return a + b + (c or 0) + (d or 0)

        result = complex_function(1, 2, c=3, d=4)

        assert result == 10
        mock_instance.get.assert_called_once()
        mock_instance.set.assert_called_once()

    @patch('src.core.cache.RedisCache')
    def test_cached_with_ttl_decorator(self, mock_redis_cache):
        """Test cached_with_ttl decorator with TTL."""
        mock_instance = Mock()
        mock_instance.get.return_value = None
        mock_instance.set.return_value = True
        mock_redis_cache.return_value = mock_instance

        @cached_with ttl=600
        def slow_operation():
            return "slow result"

        result = slow_operation()

        assert result == "slow result"
        mock_instance.get.assert_called_once()
        # Verify TTL was passed to set call
        call_args = mock_instance.set.call_args
        assert call_args[1]['ttl'] == 600

    @patch('src.core.cache.RedisCache')
    def test_cache_result_with_exception(self, mock_redis_cache):
        """Test cache_result decorator when function raises exception."""
        mock_instance = Mock()
        mock_instance.get.return_value = None
        mock_redis_cache.return_value = mock_instance

        @cache_result(key_prefix="test", ttl=300)
        def failing_function():
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            failing_function()

        mock_instance.get.assert_called_once()
        mock_instance.set.assert_not_called()

    @patch('src.core.cache.RedisCache')
    def test_cache_result_key_generation(self, mock_redis_cache):
        """Test cache key generation for decorator."""
        mock_instance = Mock()
        mock_instance.get.return_value = None
        mock_instance.set.return_value = True
        mock_redis_cache.return_value = mock_instance

        @cache_result(key_prefix="myfunc", ttl=300)
        def test_function(param1: str, param2: int):
            return f"{param1}_{param2}"

        test_function("hello", 42)

        # Verify key was generated correctly
        call_args = mock_instance.get.call_args
        key = call_args[0][0]
        assert "myfunc" in key
        assert "hello" in key
        assert "42" in key


class TestUtilityFunctions:
    """Test cache utility functions."""

    def test_generate_cache_key_function(self):
        """Test standalone generate_cache_key function."""
        key = generate_cache_key("test", {"a": 1, "b": "two"})
        assert key == "test:a=1:b=two"

    def test_generate_cache_key_with_prefix(self):
        """Test standalone generate_cache_key with prefix."""
        key = generate_cache_key("test", {"a": 1}, prefix="app")
        assert key == "app:test:a=1"

    @patch('src.core.cache.RedisCache')
    def test_cache_result_without_parentheses(self, mock_redis_cache):
        """Test cache_result decorator used without parentheses."""
        mock_instance = Mock()
        mock_instance.get.return_value = None
        mock_instance.set.return_value = True
        mock_redis_cache.return_value = mock_instance

        @cache_result
        def simple_func(x):
            return x * 2

        result = simple_func(5)
        assert result == 10

    def test_cache_error_hierarchy(self):
        """Test that cache errors inherit correctly."""
        assert issubclass(CacheKeyError, CacheError)
        assert issubclass(CacheSerializationError, CacheError)

    def test_cache_error_str_representation(self):
        """Test error string representations."""
        error = CacheError("Test message")
        assert str(error) == "Test message"

        key_error = CacheKeyError("Invalid key")
        assert str(key_error) == "Invalid key"

        serial_error = CacheSerializationError("Serialization failed")
        assert str(serial_error) == "Serialization failed"


class TestCacheEdgeCases:
    """Test edge cases and error conditions."""

    def test_key_generator_with_empty_prefix(self):
        """Test key generator with empty prefix."""
        generator = CacheKeyGenerator(prefix="")
        key = generator.generate_key("test", {})
        assert key == "test"

    def test_key_generator_with_none_params(self):
        """Test key generator with None params dict."""
        generator = CacheKeyGenerator()
        with pytest.raises(CacheKeyError):
            generator.generate_key("test", None)

    def test_serializer_with_bytes(self):
        """Test serializer with bytes input."""
        serializer = CacheSerializer()
        data = b"test bytes"
        serialized = serializer.serialize(data)
        # Should convert bytes to string
        assert isinstance(serialized, str)

    def test_deserialize_bytes_input(self):
        """Test deserializer with bytes input."""
        serializer = CacheSerializer()
        data = b'"test string"'
        deserialized = serializer.deserialize(data)
        assert deserialized == "test string"

    @patch('src.core.cache.RedisCache')
    def test_cache_decorator_with_none_return(self, mock_redis_cache):
        """Test cache decorator with None return value."""
        mock_instance = Mock()
        mock_instance.get.return_value = None
        mock_instance.set.return_value = True
        mock_redis_cache.return_value = mock_instance

        @cache_result(key_prefix="test", ttl=300)
        def returns_none():
            return None

        result = returns_none()
        assert result is None
        mock_instance.set.assert_called_once()
        # Check that None was properly serialized
        call_args = mock_instance.set.call_args
        value = call_args[0][1]
        assert value == "null"  # JSON representation of None