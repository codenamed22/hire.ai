"""
Dependency injection container for the Hire.AI agent system.

This module provides a lightweight dependency injection system that:
- Manages service lifetimes (singleton, transient, scoped)
- Handles dependency resolution
- Supports factory patterns
- Enables easier testing and modularity

Based on industry best practices from frameworks like Spring and .NET Core DI.
"""

from typing import Any, Callable, Dict, Type, TypeVar, Optional, Union, get_type_hints
from abc import ABC, abstractmethod
from enum import Enum
import inspect
import threading
from contextlib import contextmanager
from functools import wraps

T = TypeVar('T')


class ServiceLifetime(Enum):
    """Service lifetime scopes."""
    SINGLETON = "singleton"
    TRANSIENT = "transient"
    SCOPED = "scoped"


class ServiceDescriptor:
    """Describes how a service should be created and managed."""
    
    def __init__(
        self,
        service_type: Type,
        implementation: Union[Type, Callable, Any],
        lifetime: ServiceLifetime = ServiceLifetime.TRANSIENT,
        factory: Optional[Callable] = None
    ):
        self.service_type = service_type
        self.implementation = implementation
        self.lifetime = lifetime
        self.factory = factory


class IServiceContainer(ABC):
    """Interface for service container."""
    
    @abstractmethod
    def register(
        self,
        service_type: Type[T],
        implementation: Union[Type[T], Callable[[], T], T],
        lifetime: ServiceLifetime = ServiceLifetime.TRANSIENT
    ) -> 'IServiceContainer':
        """Register a service with the container."""
        pass
    
    @abstractmethod
    def register_factory(
        self,
        service_type: Type[T],
        factory: Callable[['IServiceContainer'], T],
        lifetime: ServiceLifetime = ServiceLifetime.TRANSIENT
    ) -> 'IServiceContainer':
        """Register a service factory."""
        pass
    
    @abstractmethod
    def get_service(self, service_type: Type[T]) -> T:
        """Get a service instance."""
        pass
    
    @abstractmethod
    def get_required_service(self, service_type: Type[T]) -> T:
        """Get a required service instance (throws if not found)."""
        pass


class ServiceContainer(IServiceContainer):
    """Implementation of dependency injection container."""
    
    def __init__(self):
        self._services: Dict[Type, ServiceDescriptor] = {}
        self._singletons: Dict[Type, Any] = {}
        self._scoped_instances: Dict[Type, Any] = {}
        self._lock = threading.RLock()
    
    def register(
        self,
        service_type: Type[T],
        implementation: Union[Type[T], Callable[[], T], T],
        lifetime: ServiceLifetime = ServiceLifetime.TRANSIENT
    ) -> 'ServiceContainer':
        """Register a service with the container."""
        with self._lock:
            descriptor = ServiceDescriptor(service_type, implementation, lifetime)
            self._services[service_type] = descriptor
        return self
    
    def register_factory(
        self,
        service_type: Type[T],
        factory: Callable[['IServiceContainer'], T],
        lifetime: ServiceLifetime = ServiceLifetime.TRANSIENT
    ) -> 'ServiceContainer':
        """Register a service factory."""
        with self._lock:
            descriptor = ServiceDescriptor(service_type, None, lifetime, factory)
            self._services[service_type] = descriptor
        return self
    
    def register_singleton(self, service_type: Type[T], implementation: Union[Type[T], T]) -> 'ServiceContainer':
        """Register a singleton service."""
        return self.register(service_type, implementation, ServiceLifetime.SINGLETON)
    
    def register_transient(self, service_type: Type[T], implementation: Type[T]) -> 'ServiceContainer':
        """Register a transient service."""
        return self.register(service_type, implementation, ServiceLifetime.TRANSIENT)
    
    def register_scoped(self, service_type: Type[T], implementation: Type[T]) -> 'ServiceContainer':
        """Register a scoped service."""
        return self.register(service_type, implementation, ServiceLifetime.SCOPED)
    
    def get_service(self, service_type: Type[T]) -> Optional[T]:
        """Get a service instance."""
        try:
            return self.get_required_service(service_type)
        except KeyError:
            return None
    
    def get_required_service(self, service_type: Type[T]) -> T:
        """Get a required service instance (throws if not found)."""
        with self._lock:
            if service_type not in self._services:
                raise KeyError(f"Service {service_type.__name__} is not registered")
            
            descriptor = self._services[service_type]
            
            # Handle singleton lifetime
            if descriptor.lifetime == ServiceLifetime.SINGLETON:
                if service_type not in self._singletons:
                    self._singletons[service_type] = self._create_instance(descriptor)
                return self._singletons[service_type]
            
            # Handle scoped lifetime
            elif descriptor.lifetime == ServiceLifetime.SCOPED:
                if service_type not in self._scoped_instances:
                    self._scoped_instances[service_type] = self._create_instance(descriptor)
                return self._scoped_instances[service_type]
            
            # Handle transient lifetime
            else:
                return self._create_instance(descriptor)
    
    def _create_instance(self, descriptor: ServiceDescriptor) -> Any:
        """Create an instance based on the service descriptor."""
        # Use factory if provided
        if descriptor.factory:
            return descriptor.factory(self)
        
        # If implementation is already an instance, return it
        if not inspect.isclass(descriptor.implementation):
            return descriptor.implementation
        
        # Create instance using constructor injection
        return self._create_with_injection(descriptor.implementation)
    
    def _create_with_injection(self, implementation_type: Type) -> Any:
        """Create instance with constructor dependency injection."""
        try:
            # Get constructor signature
            sig = inspect.signature(implementation_type.__init__)
            parameters = sig.parameters
            
            # Skip 'self' parameter
            param_names = [name for name in parameters.keys() if name != 'self']
            
            if not param_names:
                # No dependencies, create directly
                return implementation_type()
            
            # Get type hints for parameters
            type_hints = get_type_hints(implementation_type.__init__)
            
            # Resolve dependencies
            kwargs = {}
            for param_name in param_names:
                param = parameters[param_name]
                
                # Get parameter type
                if param_name in type_hints:
                    param_type = type_hints[param_name]
                    
                    # Try to resolve dependency
                    dependency = self.get_service(param_type)
                    if dependency is not None:
                        kwargs[param_name] = dependency
                    elif param.default is not inspect.Parameter.empty:
                        # Use default value if available
                        kwargs[param_name] = param.default
                    else:
                        raise ValueError(f"Cannot resolve dependency {param_type} for parameter {param_name}")
                elif param.default is not inspect.Parameter.empty:
                    kwargs[param_name] = param.default
                else:
                    raise ValueError(f"No type hint found for parameter {param_name}")
            
            return implementation_type(**kwargs)
            
        except Exception as e:
            raise RuntimeError(f"Failed to create instance of {implementation_type.__name__}: {str(e)}") from e
    
    @contextmanager
    def create_scope(self):
        """Create a new dependency injection scope."""
        old_scoped = self._scoped_instances.copy()
        self._scoped_instances.clear()
        try:
            yield self
        finally:
            self._scoped_instances = old_scoped
    
    def clear_singletons(self):
        """Clear all singleton instances (useful for testing)."""
        with self._lock:
            self._singletons.clear()
    
    def clear_scoped(self):
        """Clear all scoped instances."""
        with self._lock:
            self._scoped_instances.clear()
    
    def is_registered(self, service_type: Type) -> bool:
        """Check if a service type is registered."""
        return service_type in self._services


# Global service container instance
_global_container: Optional[ServiceContainer] = None
_container_lock = threading.RLock()


def get_container() -> ServiceContainer:
    """Get the global service container."""
    global _global_container
    with _container_lock:
        if _global_container is None:
            _global_container = ServiceContainer()
        return _global_container


def set_container(container: ServiceContainer):
    """Set the global service container."""
    global _global_container
    with _container_lock:
        _global_container = container


def reset_container():
    """Reset the global service container (useful for testing)."""
    global _global_container
    with _container_lock:
        _global_container = None


# Decorators for dependency injection
def injectable(cls: Type[T]) -> Type[T]:
    """Mark a class as injectable."""
    # This decorator can be used to mark classes that support DI
    # For now, it's just a marker, but could be extended for auto-registration
    cls._injectable = True
    return cls


def inject(service_type: Type[T]) -> T:
    """Inject a service dependency."""
    return get_container().get_required_service(service_type)


def inject_optional(service_type: Type[T]) -> Optional[T]:
    """Inject an optional service dependency."""
    return get_container().get_service(service_type)


# Decorator for method injection
def injected(func: Callable) -> Callable:
    """Decorator that performs dependency injection on method parameters."""
    sig = inspect.signature(func)
    type_hints = get_type_hints(func)
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Resolve dependencies for parameters not provided
        container = get_container()
        
        for param_name, param in sig.parameters.items():
            if param_name not in kwargs and param_name in type_hints:
                param_type = type_hints[param_name]
                dependency = container.get_service(param_type)
                if dependency is not None:
                    kwargs[param_name] = dependency
        
        return func(*args, **kwargs)
    
    return wrapper


# Common service registration helpers
def configure_core_services(container: ServiceContainer):
    """Configure core services for the Hire.AI system."""
    from .config import AgentConfig, get_config
    from .logging_config import get_logger
    
    # Register configuration as singleton
    container.register_singleton(AgentConfig, get_config())
    
    # Register logger factory
    container.register_factory(
        logging.Logger,
        lambda c: get_logger("hire.ai"),
        ServiceLifetime.SINGLETON
    )


def configure_agent_services(container: ServiceContainer):
    """Configure agent-related services."""
    from ..tools.scraper_tool import JobScraperTool
    from ..job_search.agent import JobSearchAgent
    
    # Register tools
    container.register_transient(JobScraperTool, JobScraperTool)
    
    # Register agents
    container.register_scoped(JobSearchAgent, JobSearchAgent)


# Example usage and testing helpers
if __name__ == "__main__":
    # Example of how to use the DI container
    
    @injectable
    class DatabaseService:
        def __init__(self):
            self.connection = "db_connection"
        
        def query(self, sql: str) -> str:
            return f"Result for: {sql}"
    
    @injectable 
    class UserService:
        def __init__(self, db: DatabaseService):
            self.db = db
        
        def get_user(self, user_id: str) -> str:
            return self.db.query(f"SELECT * FROM users WHERE id = {user_id}")
    
    # Setup container
    container = ServiceContainer()
    container.register_singleton(DatabaseService, DatabaseService)
    container.register_transient(UserService, UserService)
    
    # Resolve services
    user_service = container.get_required_service(UserService)
    result = user_service.get_user("123")
    print(result)  # Should print: Result for: SELECT * FROM users WHERE id = 123