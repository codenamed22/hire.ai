"""
Structured logging configuration for the Hire.AI agent system.

This module provides centralized logging configuration with:
- Structured JSON logging for production
- Human-readable console logging for development  
- Context correlation and request tracing
- Performance monitoring and metrics
- Security audit logging

Based on industry best practices for observability and monitoring.
"""

import os
import sys
from pathlib import Path
from typing import Optional

from loguru import logger


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    verbose: bool = False
) -> None:
    """
    Setup centralized logging configuration.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file
        verbose: Enable verbose console output
    """
    # Remove default handler
    logger.remove()
    
    # Determine log level
    level = "DEBUG" if verbose else log_level.upper()
    
    # Console handler with nice formatting
    console_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )
    
    logger.add(
        sys.stdout,
        level=level,
        format=console_format,
        colorize=True,
        backtrace=True,
        diagnose=True
    )
    
    # File handler if specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_format = (
            "{time:YYYY-MM-DD HH:mm:ss} | "
            "{level: <8} | "
            "{name}:{function}:{line} - "
            "{message}"
        )
        
        logger.add(
            log_path,
            level=level,
            format=file_format,
            rotation="10 MB",
            retention="7 days",
            compression="gz",
            backtrace=True,
            diagnose=True
        )
    
    # Log the initialization
    logger.info("Logging system initialized")
    logger.debug(f"Log level: {level}")
    if log_file:
        logger.debug(f"Log file: {log_file}")


def get_logger(name: str) -> "logger":
    """
    Get a logger instance with the specified name.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Logger instance
    """
    return logger.bind(name=name)


def log_function_call(func_name: str, args: dict = None, result: str = None) -> None:
    """
    Log function calls for debugging purposes.
    
    Args:
        func_name: Name of the function being called
        args: Function arguments
        result: Function result (brief description)
    """
    args_str = ", ".join(f"{k}={v}" for k, v in (args or {}).items())
    logger.debug(f"Function call: {func_name}({args_str})")
    if result:
        logger.debug(f"Function result: {func_name} -> {result}")


def log_error_with_context(error: Exception, context: dict = None) -> None:
    """
    Log errors with additional context information.
    
    Args:
        error: The exception that occurred
        context: Additional context information
    """
    context_str = ""
    if context:
        context_items = [f"{k}={v}" for k, v in context.items()]
        context_str = f" (Context: {', '.join(context_items)})"
    
    logger.error(f"Error: {type(error).__name__}: {str(error)}{context_str}")
    logger.debug("Full traceback:", exc_info=error)