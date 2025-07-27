"""
Advanced configuration management for the Hire.AI agent system.

This module provides enterprise-grade configuration management with:
- Environment-based configuration
- Configuration validation and type checking
- Hot reloading capabilities
- Configuration encryption for sensitive values
- Configuration profiles (dev, staging, prod)

Based on 12-factor app principles and cloud-native best practices.
"""

import os
import json
import yaml
from typing import Dict, Any, Optional, Type, TypeVar, Union, List
from pathlib import Path
from dataclasses import dataclass, field, fields
from enum import Enum
import hashlib
import base64
from cryptography.fernet import Fernet
import threading
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .exceptions import ConfigurationError
from .logging_config import get_logger

T = TypeVar('T')
logger = get_logger(__name__)


class Environment(Enum):
    """Deployment environments."""
    DEVELOPMENT = "development"
    STAGING = "staging"  
    PRODUCTION = "production"
    TESTING = "testing"


class ConfigFormat(Enum):
    """Supported configuration file formats."""
    JSON = "json"
    YAML = "yaml"
    ENV = "env"


@dataclass
class DatabaseConfig:
    """Database configuration."""
    host: str = "localhost"
    port: int = 5432
    name: str = "hire_ai"
    username: str = "postgres"
    password: str = ""
    ssl_mode: str = "prefer"
    pool_size: int = 10
    max_overflow: int = 20
    
    def get_connection_string(self) -> str:
        """Get database connection string."""
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.name}?sslmode={self.ssl_mode}"


@dataclass
class RedisConfig:
    """Redis configuration."""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    ssl: bool = False
    socket_timeout: float = 5.0
    
    def get_connection_params(self) -> Dict[str, Any]:
        """Get Redis connection parameters."""
        params = {
            "host": self.host,
            "port": self.port,
            "db": self.db,
            "socket_timeout": self.socket_timeout
        }
        if self.password:
            params["password"] = self.password
        if self.ssl:
            params["ssl"] = True
        return params


@dataclass
class SecurityConfig:
    """Security configuration."""
    secret_key: str = ""
    jwt_secret: str = ""
    password_salt: str = ""
    encryption_key: Optional[str] = None
    session_timeout: int = 3600
    max_login_attempts: int = 5
    lockout_duration: int = 900
    
    def __post_init__(self):
        """Validate security configuration."""
        if not self.secret_key:
            raise ConfigurationError("SECRET_KEY is required for security")
        
        if len(self.secret_key) < 32:
            raise ConfigurationError("SECRET_KEY must be at least 32 characters")


@dataclass
class MonitoringConfig:
    """Monitoring and observability configuration."""
    enable_metrics: bool = True
    enable_tracing: bool = True
    metrics_port: int = 9090
    jaeger_endpoint: Optional[str] = None
    prometheus_endpoint: Optional[str] = None
    log_level: str = "INFO"
    structured_logging: bool = True


@dataclass
class AdvancedConfig:
    """Advanced application configuration."""
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    testing: bool = False
    
    # Service configuration
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    
    # Database
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    
    # Cache
    redis: RedisConfig = field(default_factory=RedisConfig)
    
    # Security
    security: SecurityConfig = field(default_factory=SecurityConfig)
    
    # Monitoring
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    
    # Feature flags
    feature_flags: Dict[str, bool] = field(default_factory=dict)
    
    # Agent configuration
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    max_agent_rounds: int = 10
    agent_timeout: int = 300
    
    # Scraper configuration
    scraper_binary_path: str = ""
    scraper_config_path: str = "config/production.json"
    default_keywords: str = "software engineer,developer,programmer"
    default_location: str = "India,Remote"
    default_max_results: int = 50
    scraper_timeout: int = 300
    
    def __post_init__(self):
        """Post-initialization validation."""
        if self.environment == Environment.PRODUCTION:
            if not self.openai_api_key:
                raise ConfigurationError("OPENAI_API_KEY is required in production")
            
            if not self.scraper_binary_path:
                raise ConfigurationError("SCRAPER_BINARY_PATH is required in production")
    
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == Environment.DEVELOPMENT
    
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == Environment.PRODUCTION


class ConfigEncryption:
    """Handle encryption/decryption of sensitive configuration values."""
    
    def __init__(self, key: Optional[str] = None):
        if key:
            self.fernet = Fernet(key.encode() if isinstance(key, str) else key)
        else:
            # Generate a key from environment or use default
            env_key = os.getenv("CONFIG_ENCRYPTION_KEY")
            if env_key:
                self.fernet = Fernet(env_key.encode())
            else:
                # Use a default key (not secure, only for development)
                default_key = Fernet.generate_key()
                self.fernet = Fernet(default_key)
                logger.warning("Using default encryption key - not secure for production")
    
    def encrypt_value(self, value: str) -> str:
        """Encrypt a configuration value."""
        if not value:
            return value
        
        encrypted = self.fernet.encrypt(value.encode())
        return base64.b64encode(encrypted).decode()
    
    def decrypt_value(self, encrypted_value: str) -> str:
        """Decrypt a configuration value."""
        if not encrypted_value:
            return encrypted_value
        
        try:
            encrypted_bytes = base64.b64decode(encrypted_value.encode())
            decrypted = self.fernet.decrypt(encrypted_bytes)
            return decrypted.decode()
        except Exception as e:
            logger.warning(f"Failed to decrypt value: {e}")
            return encrypted_value


class ConfigWatcher(FileSystemEventHandler):
    """File system watcher for configuration hot reloading."""
    
    def __init__(self, config_manager: 'AdvancedConfigManager'):
        self.config_manager = config_manager
        self.last_modified = {}
    
    def on_modified(self, event):
        """Handle file modification events."""
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        if file_path.suffix in ['.json', '.yaml', '.yml', '.env']:
            # Debounce rapid file changes
            current_time = time.time()
            last_mod = self.last_modified.get(file_path, 0)
            
            if current_time - last_mod > 1.0:  # 1 second debounce
                self.last_modified[file_path] = current_time
                logger.info(f"Configuration file changed: {file_path}")
                self.config_manager.reload_configuration()


class AdvancedConfigManager:
    """Advanced configuration manager with hot reloading and encryption."""
    
    def __init__(
        self,
        config_paths: Optional[List[str]] = None,
        encryption_key: Optional[str] = None,
        enable_hot_reload: bool = False
    ):
        self.config_paths = config_paths or []
        self.encryption = ConfigEncryption(encryption_key)
        self.enable_hot_reload = enable_hot_reload
        self._config: Optional[AdvancedConfig] = None
        self._config_lock = threading.RLock()
        self._observer: Optional[Observer] = None
        
        # Default config paths
        if not self.config_paths:
            self.config_paths = [
                "config/default.yaml",
                "config/local.yaml", 
                f"config/{self._get_environment().value}.yaml",
                ".env"
            ]
    
    def _get_environment(self) -> Environment:
        """Get current environment from environment variable."""
        env_str = os.getenv("ENVIRONMENT", "development").lower()
        try:
            return Environment(env_str)
        except ValueError:
            logger.warning(f"Unknown environment '{env_str}', defaulting to development")
            return Environment.DEVELOPMENT
    
    def load_configuration(self) -> AdvancedConfig:
        """Load configuration from all sources."""
        with self._config_lock:
            config_data = {}
            
            # Load from files
            for config_path in self.config_paths:
                file_data = self._load_config_file(config_path)
                if file_data:
                    config_data.update(file_data)
            
            # Override with environment variables
            env_data = self._load_from_environment()
            config_data.update(env_data)
            
            # Decrypt sensitive values
            config_data = self._decrypt_sensitive_values(config_data)
            
            # Create configuration object
            self._config = self._create_config_object(config_data)
            
            # Setup hot reloading
            if self.enable_hot_reload and not self._observer:
                self._setup_hot_reload()
            
            logger.info("Configuration loaded successfully")
            return self._config
    
    def _load_config_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Load configuration from a file."""
        path = Path(file_path)
        if not path.exists():
            return None
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                if path.suffix in ['.yaml', '.yml']:
                    return yaml.safe_load(f)
                elif path.suffix == '.json':
                    return json.load(f)
                elif path.suffix == '.env' or path.name.startswith('.env'):
                    return self._parse_env_file(f)
            
        except Exception as e:
            logger.error(f"Failed to load config file {file_path}: {e}")
            return None
    
    def _parse_env_file(self, file_handle) -> Dict[str, Any]:
        """Parse environment file."""
        config = {}
        for line in file_handle:
            line = line.strip()
            if line and not line.startswith('#'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    
                    # Convert to nested structure
                    if '.' in key:
                        parts = key.split('.')
                        current = config
                        for part in parts[:-1]:
                            if part not in current:
                                current[part] = {}
                            current = current[part]
                        current[parts[-1]] = value
                    else:
                        config[key] = value
        
        return config
    
    def _load_from_environment(self) -> Dict[str, Any]:
        """Load configuration from environment variables."""
        config = {}
        
        # Map environment variables to config structure
        env_mapping = {
            'ENVIRONMENT': 'environment',
            'DEBUG': 'debug',
            'HOST': 'host',
            'PORT': 'port',
            'WORKERS': 'workers',
            
            # Database
            'DATABASE_HOST': 'database.host',
            'DATABASE_PORT': 'database.port',
            'DATABASE_NAME': 'database.name',
            'DATABASE_USERNAME': 'database.username',
            'DATABASE_PASSWORD': 'database.password',
            
            # Redis
            'REDIS_HOST': 'redis.host',
            'REDIS_PORT': 'redis.port',
            'REDIS_PASSWORD': 'redis.password',
            
            # Security
            'SECRET_KEY': 'security.secret_key',
            'JWT_SECRET': 'security.jwt_secret',
            
            # OpenAI
            'OPENAI_API_KEY': 'openai_api_key',
            'OPENAI_BASE_URL': 'openai_base_url',
            'OPENAI_MODEL': 'openai_model',
            
            # Monitoring
            'LOG_LEVEL': 'monitoring.log_level',
            'ENABLE_METRICS': 'monitoring.enable_metrics',
        }
        
        for env_key, config_key in env_mapping.items():
            value = os.getenv(env_key)
            if value is not None:
                # Convert types
                if value.lower() in ['true', 'false']:
                    value = value.lower() == 'true'
                elif value.isdigit():
                    value = int(value)
                
                # Set nested value
                keys = config_key.split('.')
                current = config
                for key in keys[:-1]:
                    if key not in current:
                        current[key] = {}
                    current = current[key]
                current[keys[-1]] = value
        
        return config
    
    def _decrypt_sensitive_values(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Decrypt sensitive configuration values."""
        sensitive_keys = [
            'database.password',
            'redis.password', 
            'security.secret_key',
            'security.jwt_secret',
            'openai_api_key'
        ]
        
        for key in sensitive_keys:
            value = self._get_nested_value(config_data, key)
            if value and isinstance(value, str) and value.startswith('encrypted:'):
                encrypted_value = value[10:]  # Remove 'encrypted:' prefix
                decrypted_value = self.encryption.decrypt_value(encrypted_value)
                self._set_nested_value(config_data, key, decrypted_value)
        
        return config_data
    
    def _get_nested_value(self, data: Dict[str, Any], key: str) -> Any:
        """Get nested value from dictionary using dot notation."""
        keys = key.split('.')
        current = data
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return None
        return current
    
    def _set_nested_value(self, data: Dict[str, Any], key: str, value: Any) -> None:
        """Set nested value in dictionary using dot notation."""
        keys = key.split('.')
        current = data
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        current[keys[-1]] = value
    
    def _create_config_object(self, config_data: Dict[str, Any]) -> AdvancedConfig:
        """Create AdvancedConfig object from dictionary."""
        try:
            # Handle nested objects
            if 'database' in config_data:
                config_data['database'] = DatabaseConfig(**config_data['database'])
            
            if 'redis' in config_data:
                config_data['redis'] = RedisConfig(**config_data['redis'])
            
            if 'security' in config_data:
                config_data['security'] = SecurityConfig(**config_data['security'])
            
            if 'monitoring' in config_data:
                config_data['monitoring'] = MonitoringConfig(**config_data['monitoring'])
            
            # Handle environment enum
            if 'environment' in config_data:
                if isinstance(config_data['environment'], str):
                    config_data['environment'] = Environment(config_data['environment'])
            
            return AdvancedConfig(**config_data)
            
        except Exception as e:
            raise ConfigurationError(f"Failed to create configuration object: {e}") from e
    
    def _setup_hot_reload(self) -> None:
        """Setup file watching for hot reloading."""
        try:
            self._observer = Observer()
            event_handler = ConfigWatcher(self)
            
            # Watch config directories
            watched_dirs = set()
            for config_path in self.config_paths:
                config_dir = Path(config_path).parent
                if config_dir.exists() and config_dir not in watched_dirs:
                    self._observer.schedule(event_handler, str(config_dir), recursive=False)
                    watched_dirs.add(config_dir)
            
            self._observer.start()
            logger.info("Configuration hot reloading enabled")
            
        except Exception as e:
            logger.error(f"Failed to setup hot reloading: {e}")
    
    def reload_configuration(self) -> None:
        """Reload configuration from all sources."""
        try:
            logger.info("Reloading configuration...")
            self.load_configuration()
            logger.info("Configuration reloaded successfully")
        except Exception as e:
            logger.error(f"Failed to reload configuration: {e}")
    
    def get_config(self) -> AdvancedConfig:
        """Get current configuration."""
        if self._config is None:
            self.load_configuration()
        return self._config
    
    def stop_hot_reload(self) -> None:
        """Stop hot reloading."""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
            logger.info("Configuration hot reloading stopped")
    
    def encrypt_sensitive_value(self, value: str) -> str:
        """Encrypt a sensitive value for storage."""
        return f"encrypted:{self.encryption.encrypt_value(value)}"


# Global configuration manager
_config_manager: Optional[AdvancedConfigManager] = None
_manager_lock = threading.RLock()


def get_config_manager() -> AdvancedConfigManager:
    """Get global configuration manager."""
    global _config_manager
    with _manager_lock:
        if _config_manager is None:
            _config_manager = AdvancedConfigManager(
                enable_hot_reload=os.getenv("ENABLE_CONFIG_HOT_RELOAD", "false").lower() == "true"
            )
        return _config_manager


def get_advanced_config() -> AdvancedConfig:
    """Get current advanced configuration."""
    return get_config_manager().get_config()


def reload_config() -> None:
    """Reload configuration from all sources."""
    get_config_manager().reload_configuration()


def set_config_manager(manager: AdvancedConfigManager) -> None:
    """Set global configuration manager."""
    global _config_manager
    with _manager_lock:
        if _config_manager and _config_manager._observer:
            _config_manager.stop_hot_reload()
        _config_manager = manager


# Environment-specific configuration loaders
def load_development_config() -> AdvancedConfig:
    """Load development configuration."""
    manager = AdvancedConfigManager(
        config_paths=[
            "config/development.yaml",
            "config/local.yaml",
            ".env.development"
        ],
        enable_hot_reload=True
    )
    return manager.load_configuration()


def load_production_config() -> AdvancedConfig:
    """Load production configuration."""
    manager = AdvancedConfigManager(
        config_paths=[
            "config/production.yaml",
            ".env.production"
        ],
        enable_hot_reload=False
    )
    return manager.load_configuration()


def load_testing_config() -> AdvancedConfig:
    """Load testing configuration."""
    manager = AdvancedConfigManager(
        config_paths=[
            "config/testing.yaml",
            ".env.testing"
        ],
        enable_hot_reload=False
    )
    return manager.load_configuration()