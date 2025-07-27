"""
Resilience patterns for the Hire.AI agent system.

This module implements enterprise-grade resilience patterns including:
- Circuit Breaker
- Retry with exponential backoff  
- Timeout handling
- Rate limiting

Based on Microsoft Azure Architecture patterns and industry best practices.
"""

import asyncio
import time
import random
from typing import Callable, Any, Optional, Dict, Type, Union, Awaitable
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
import logging
from contextlib import asynccontextmanager

from .exceptions import (
    CircuitBreakerError, RetryableError, TimeoutError as AgentTimeoutError,
    RateLimitError, ExternalServiceError
)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class RetryConfig:
    """Configuration for retry logic."""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_exceptions: tuple = (RetryableError, ExternalServiceError, ConnectionError)


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    expected_exception: Type[Exception] = Exception
    success_threshold: int = 3  # For half-open state


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    max_calls: int = 100
    time_window: float = 60.0  # seconds
    burst_size: int = 10


class CircuitBreaker:
    """Circuit breaker implementation."""
    
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.logger = logging.getLogger(f"{__name__}.CircuitBreaker")
    
    def __call__(self, func: Callable) -> Callable:
        """Decorator to apply circuit breaker to a function."""
        if asyncio.iscoroutinefunction(func):
            return self._async_wrapper(func)
        else:
            return self._sync_wrapper(func)
    
    def _sync_wrapper(self, func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    self.logger.info("Circuit breaker entering HALF_OPEN state")
                else:
                    raise CircuitBreakerError(
                        f"Circuit breaker is OPEN for {func.__name__}",
                        service_name=func.__name__
                    )
            
            try:
                result = func(*args, **kwargs)
                self._on_success()
                return result
            except self.config.expected_exception as e:
                self._on_failure()
                raise
        
        return wrapper
    
    def _async_wrapper(self, func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    self.logger.info("Circuit breaker entering HALF_OPEN state")
                else:
                    raise CircuitBreakerError(
                        f"Circuit breaker is OPEN for {func.__name__}",
                        service_name=func.__name__
                    )
            
            try:
                result = await func(*args, **kwargs)
                self._on_success()
                return result
            except self.config.expected_exception as e:
                self._on_failure()
                raise
        
        return wrapper
    
    def _should_attempt_reset(self) -> bool:
        """Check if circuit breaker should attempt to reset."""
        return (time.time() - self.last_failure_time) >= self.config.recovery_timeout
    
    def _on_success(self):
        """Handle successful execution."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.logger.info("Circuit breaker reset to CLOSED state")
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0
    
    def _on_failure(self):
        """Handle failed execution."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self.logger.warning("Circuit breaker opened from HALF_OPEN state")
        elif (self.state == CircuitState.CLOSED and 
              self.failure_count >= self.config.failure_threshold):
            self.state = CircuitState.OPEN
            self.logger.warning(f"Circuit breaker opened after {self.failure_count} failures")


class RateLimiter:
    """Token bucket rate limiter."""
    
    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.tokens = config.max_calls
        self.last_refill = time.time()
        self.logger = logging.getLogger(f"{__name__}.RateLimiter")
    
    def acquire(self, tokens: int = 1) -> bool:
        """Acquire tokens from the bucket."""
        self._refill()
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
    
    def _refill(self):
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        
        if elapsed > 0:
            # Calculate tokens to add
            tokens_to_add = (elapsed / self.config.time_window) * self.config.max_calls
            self.tokens = min(self.config.max_calls, self.tokens + tokens_to_add)
            self.last_refill = now
    
    def __call__(self, func: Callable) -> Callable:
        """Decorator to apply rate limiting to a function."""
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not self.acquire():
                raise RateLimitError(
                    f"Rate limit exceeded for {func.__name__}",
                    retry_after=int(self.config.time_window)
                )
            return func(*args, **kwargs)
        
        return wrapper


def retry_with_backoff(config: RetryConfig = None):
    """Decorator for retry logic with exponential backoff."""
    if config is None:
        config = RetryConfig()
    
    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            return _async_retry_wrapper(func, config)
        else:
            return _sync_retry_wrapper(func, config)
    
    return decorator


def _sync_retry_wrapper(func: Callable, config: RetryConfig) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger = logging.getLogger(f"{__name__}.retry")
        last_exception = None
        
        for attempt in range(config.max_attempts):
            try:
                return func(*args, **kwargs)
            except config.retryable_exceptions as e:
                last_exception = e
                
                if attempt == config.max_attempts - 1:
                    logger.error(f"Final retry attempt failed for {func.__name__}: {e}")
                    raise
                
                delay = _calculate_delay(attempt, config)
                logger.info(f"Retry {attempt + 1}/{config.max_attempts} for {func.__name__} in {delay:.2f}s")
                time.sleep(delay)
            except Exception as e:
                # Non-retryable exception
                logger.error(f"Non-retryable error in {func.__name__}: {e}")
                raise
        
        # This should never be reached
        raise last_exception
    
    return wrapper


def _async_retry_wrapper(func: Callable, config: RetryConfig) -> Callable:
    @wraps(func)
    async def wrapper(*args, **kwargs):
        logger = logging.getLogger(f"{__name__}.retry")
        last_exception = None
        
        for attempt in range(config.max_attempts):
            try:
                return await func(*args, **kwargs)
            except config.retryable_exceptions as e:
                last_exception = e
                
                if attempt == config.max_attempts - 1:
                    logger.error(f"Final retry attempt failed for {func.__name__}: {e}")
                    raise
                
                delay = _calculate_delay(attempt, config)
                logger.info(f"Retry {attempt + 1}/{config.max_attempts} for {func.__name__} in {delay:.2f}s")
                await asyncio.sleep(delay)
            except Exception as e:
                # Non-retryable exception
                logger.error(f"Non-retryable error in {func.__name__}: {e}")
                raise
        
        # This should never be reached
        raise last_exception
    
    return wrapper


def _calculate_delay(attempt: int, config: RetryConfig) -> float:
    """Calculate delay for retry attempt."""
    delay = config.base_delay * (config.exponential_base ** attempt)
    delay = min(delay, config.max_delay)
    
    if config.jitter:
        # Add jitter to prevent thundering herd
        jitter = random.uniform(0, delay * 0.1)
        delay += jitter
    
    return delay


def timeout(seconds: float):
    """Decorator to add timeout to function execution."""
    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            return _async_timeout_wrapper(func, seconds)
        else:
            return _sync_timeout_wrapper(func, seconds)
    
    return decorator


def _sync_timeout_wrapper(func: Callable, timeout_seconds: float) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs):
        # For sync functions, we can't easily implement timeout without threading
        # This is a simplified version - consider using concurrent.futures for real timeout
        start_time = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start_time
        
        if elapsed > timeout_seconds:
            logging.getLogger(f"{__name__}.timeout").warning(
                f"{func.__name__} took {elapsed:.2f}s (timeout: {timeout_seconds}s)"
            )
        
        return result
    
    return wrapper


def _async_timeout_wrapper(func: Callable, timeout_seconds: float) -> Callable:
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            raise AgentTimeoutError(
                f"{func.__name__} timed out after {timeout_seconds} seconds",
                timeout_duration=int(timeout_seconds)
            )
    
    return wrapper


@asynccontextmanager
async def resilient_operation(
    circuit_config: CircuitBreakerConfig = None,
    retry_config: RetryConfig = None,
    rate_limit_config: RateLimitConfig = None,
    timeout_seconds: float = None
):
    """Context manager for applying multiple resilience patterns."""
    decorators = []
    
    if circuit_config:
        decorators.append(CircuitBreaker(circuit_config))
    
    if retry_config:
        decorators.append(retry_with_backoff(retry_config))
    
    if rate_limit_config:
        decorators.append(RateLimiter(rate_limit_config))
    
    if timeout_seconds:
        decorators.append(timeout(timeout_seconds))
    
    # This is a simplified version - in practice, you'd want to compose decorators properly
    yield decorators


# Common configurations for different scenarios
DEFAULT_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    base_delay=1.0,
    max_delay=30.0
)

DEFAULT_CIRCUIT_BREAKER_CONFIG = CircuitBreakerConfig(
    failure_threshold=5,
    recovery_timeout=60.0
)

DEFAULT_RATE_LIMIT_CONFIG = RateLimitConfig(
    max_calls=100,
    time_window=60.0
)

# Pre-configured resilience patterns
def resilient_external_service():
    """Resilience config for external service calls."""
    return {
        'retry_config': RetryConfig(
            max_attempts=3,
            base_delay=2.0,
            max_delay=60.0,
            retryable_exceptions=(ExternalServiceError, ConnectionError, TimeoutError)
        ),
        'circuit_config': CircuitBreakerConfig(
            failure_threshold=5,
            recovery_timeout=120.0,
            expected_exception=Exception
        ),
        'timeout_seconds': 30.0
    }


def resilient_agent_operation():
    """Resilience config for agent operations."""
    return {
        'retry_config': RetryConfig(
            max_attempts=2,
            base_delay=1.0,
            max_delay=10.0,
            retryable_exceptions=(RetryableError,)
        ),
        'timeout_seconds': 60.0
    }