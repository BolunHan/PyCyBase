from collections.abc import Callable
from typing import Any


class EnvConfigContext:
    """Context manager for temporary environment configuration changes."""

    def __init__(self, **kwargs) -> None:
        """
        Initialize the context with configuration changes.

        Args:
            **kwargs: Configuration key-value pairs to set temporarily
        """
        ...

    def __enter__(self) -> EnvConfigContext:
        """Enter the context, applying configuration changes."""
        ...

    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: Any) -> None:
        """Exit the context, reverting configuration changes."""
        ...

    def __call__(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """Decorator to apply the context to a function."""
        ...

    def __or__(self, other: EnvConfigContext) -> EnvConfigContext:
        """
        Combine two EnvConfigContext instances.

        Args:
            other: Another EnvConfigContext instance

        Returns:
            A new EnvConfigContext with combined configurations
        """
        ...

    def __invert__(self) -> EnvConfigContext:
        """
        Invert the EnvConfigContext.

        Returns:
            A new EnvConfigContext that reverts the configurations set in the original.
        """
        ...
