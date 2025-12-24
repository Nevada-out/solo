from typing import Any, Dict, Optional


def validate_docstring(obj: Any) -> bool:
    """
    Validate if an object has a properly formatted docstring.

    A valid docstring must:
    - Be a non-empty string
    - Start with a one-line summary (first line non-empty)
    - For multi-line: have blank line after summary and before closing

    Args:
        obj: Python object (function, class, module) to validate

    Returns:
        bool: True if docstring is valid, False otherwise

    Example:
        >>> def good_func():
        ...     """Summary.\n\n    Extended description."""
        ...     pass
        >>> validate_docstring(good_func)
        True
    """
    doc = getattr(obj, '__doc__', None)
    if not doc or not isinstance(doc, str) or not doc.strip():
        return False
    
    lines = doc.strip().split('\n')
    if not lines or not lines[0].strip():
        return False
    
    # Check for proper multi-line structure if more than one line
    if len(lines) > 1:
        # Blank line after summary
        if lines[1].strip():
            return False
        # Blank line before end if extended content
        if len(lines) > 2 and not lines[-2].strip():
            pass  # Good structure
        elif len(lines) > 2:
            return False
    
    return True


def generate_template(kind: str = 'function') -> str:
    """
    Generate a standard docstring template for different Python objects.

    Args:
        kind: Type of object ('function', 'class', 'module')

    Returns:
        str: Formatted docstring template

    Raises:
        ValueError: If invalid kind specified
    """
    templates = {
        'function': '''"""
{summary}

Args:
    arg1: Description of arg1
    arg2 (int, optional): Description of arg2. Defaults to 0.

Returns:
    Description of return value

Raises:
    ValueError: If invalid input

Example:
    >>> result = my_function(arg1="value")
"""''',
        'class': '''"""
Class description.

Attributes:
    attr1: Description

Methods:
    method1:
        Brief description.
"""''',
        'module': '''"""
Module description.

Classes:
* MyClass

Functions:
* my_function
"""'''
    }
    
    template = templates.get(kind.lower())
    if not template:
        raise ValueError(f"Unsupported kind: {kind}. Use 'function', 'class', or 'module'")
    
    return template


def add_missing_docs(func: callable) -> callable:
    """
    Decorator to add a basic docstring to functions missing documentation.

    Args:
        func: Function to decorate

    Returns:
        Wrapped function with docstring if missing
    """
    if not getattr(func, '__doc__', None):
        func.__doc__ = "Customizable function - please update this docstring."
    return func