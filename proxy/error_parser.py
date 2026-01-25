#!/usr/bin/env python3
"""
Applesoft BASIC Error Parser

Parses Apple II screen output to detect and categorize BASIC errors.

Applesoft Error Format:
  ?ERROR TYPE IN LINE
  or
  ?ERROR TYPE (no line number for immediate mode)

Examples:
  ?SYNTAX ERROR IN 10
  ?ILLEGAL QUANTITY ERROR IN 20
  ?TYPE MISMATCH ERROR IN 30
"""

import re
from typing import List, Dict, Optional

# All Applesoft BASIC error types
APPLESOFT_ERRORS = [
    'NEXT WITHOUT FOR',
    'SYNTAX',
    'RETURN WITHOUT GOSUB',
    'OUT OF DATA',
    'ILLEGAL QUANTITY',
    'OVERFLOW',
    'OUT OF MEMORY',
    'UNDEF\'D STATEMENT',
    'BAD SUBSCRIPT',
    'REDIM\'D ARRAY',
    'DIVISION BY ZERO',
    'ILLEGAL DIRECT',
    'TYPE MISMATCH',
    'STRING TOO LONG',
    'FORMULA TOO COMPLEX',
    'CAN\'T CONTINUE',
    'UNDEF\'D FUNCTION',
    'REENTER',
    'BREAK',  # Not really an error, but Ctrl+C shows this
]

# Error message pattern
# Matches: ?ERROR TYPE ERROR IN LINE or ?ERROR TYPE ERROR
ERROR_PATTERN = re.compile(
    r'\?([A-Z\' ]+?)(?:\s+ERROR)?(?:\s+IN\s+(\d+))?',
    re.IGNORECASE
)


def parse_error(line: str) -> Optional[Dict]:
    """Parse a single line for Applesoft errors.

    Args:
        line: A line of text from the Apple II screen

    Returns:
        Dict with error info, or None if no error found:
        {
            'type': 'SYNTAX',
            'line': 10,  # or None for immediate mode
            'message': '?SYNTAX ERROR IN 10',
            'raw': original line
        }
    """
    line = line.strip()

    # Must start with ? for error
    if not line.startswith('?'):
        return None

    match = ERROR_PATTERN.match(line)
    if not match:
        return None

    error_type = match.group(1).strip()
    line_num = int(match.group(2)) if match.group(2) else None

    # Clean up error type - remove trailing "ERROR" if present
    if error_type.endswith(' ERROR'):
        error_type = error_type[:-6].strip()

    # Validate it's a known error type
    error_upper = error_type.upper()
    matched_error = None
    for known_error in APPLESOFT_ERRORS:
        if known_error == error_upper or error_upper in known_error or known_error in error_upper:
            matched_error = known_error
            break

    if matched_error is None:
        # Unknown error format, but still starts with ?
        matched_error = error_type.upper()

    return {
        'type': matched_error,
        'line': line_num,
        'message': line,
        'raw': line,
    }


def parse_errors(screen_lines: List[str]) -> List[Dict]:
    """Parse screen output for all Applesoft errors.

    Args:
        screen_lines: List of screen lines (from screen_reader)

    Returns:
        List of error dicts, empty if no errors found
    """
    errors = []

    for line in screen_lines:
        error = parse_error(line)
        if error:
            errors.append(error)

    return errors


def parse_screen_text(screen_text: str) -> List[Dict]:
    """Parse screen text (single string) for errors.

    Args:
        screen_text: Screen content as single string with newlines

    Returns:
        List of error dicts
    """
    lines = screen_text.split('\n')
    return parse_errors(lines)


def has_errors(screen_lines: List[str]) -> bool:
    """Quick check if screen has any errors."""
    for line in screen_lines:
        if line.strip().startswith('?'):
            return True
    return False


def get_error_summary(errors: List[Dict]) -> str:
    """Generate human-readable error summary.

    Args:
        errors: List of error dicts from parse_errors()

    Returns:
        Formatted string describing all errors
    """
    if not errors:
        return "No errors detected."

    lines = []
    for i, error in enumerate(errors, 1):
        if error['line'] is not None:
            lines.append(f"{i}. {error['type']} error on line {error['line']}")
        else:
            lines.append(f"{i}. {error['type']} error (immediate mode)")

    return '\n'.join(lines)


def get_fix_suggestion(error: Dict) -> str:
    """Suggest fix for common errors.

    Args:
        error: Single error dict

    Returns:
        Suggestion string
    """
    error_type = error['type'].upper()

    suggestions = {
        'SYNTAX': "Check for typos, missing quotes, or invalid characters",
        'ILLEGAL QUANTITY': "Value is out of range (e.g., negative PEEK, COLOR > 255)",
        'TYPE MISMATCH': "Wrong variable type (string vs number)",
        'UNDEF\'D STATEMENT': "GOTO/GOSUB to non-existent line number",
        'OUT OF DATA': "READ statement needs more DATA",
        'NEXT WITHOUT FOR': "Missing or mismatched FOR statement",
        'RETURN WITHOUT GOSUB': "RETURN without corresponding GOSUB",
        'DIVISION BY ZERO': "Attempted to divide by zero",
        'OVERFLOW': "Number too large (>1.7E38)",
        'OUT OF MEMORY': "Program or variables too large",
        'BAD SUBSCRIPT': "Array index out of bounds",
        'REDIM\'D ARRAY': "Cannot DIM an array twice",
        'ILLEGAL DIRECT': "Command not allowed in immediate mode",
        'STRING TOO LONG': "String exceeds 255 characters",
        'FORMULA TOO COMPLEX': "Expression too deeply nested",
        'CAN\'T CONTINUE': "Cannot CONT after editing or error",
        'UNDEF\'D FUNCTION': "DEF FN not found",
    }

    return suggestions.get(error_type, "Unknown error - check BASIC syntax")


# Test code
if __name__ == '__main__':
    print("Applesoft Error Parser")
    print()

    # Test cases
    test_lines = [
        "?SYNTAX ERROR IN 10",
        "?ILLEGAL QUANTITY ERROR IN 20",
        "?TYPE MISMATCH ERROR IN 30",
        "?OUT OF DATA ERROR IN 40",
        "?DIVISION BY ZERO ERROR IN 50",
        "?OVERFLOW ERROR",
        "?OUT OF MEMORY ERROR",
        "?UNDEF'D STATEMENT ERROR IN 60",
        "?BAD SUBSCRIPT ERROR",
        "?REDIM'D ARRAY ERROR",
        "?UNDEF'D FUNCTION ERROR",
        "?RETURN WITHOUT GOSUB ERROR",
        "?NEXT WITHOUT FOR ERROR IN 100",
        "HELLO WORLD",  # Not an error
        "]",  # BASIC prompt, not an error
        "",  # Empty line
    ]

    print("Parsing test lines:")
    print("-" * 50)

    for line in test_lines:
        error = parse_error(line)
        if error:
            print(f"  '{line}'")
            print(f"    -> {error['type']} on line {error['line']}")
            print(f"    Suggestion: {get_fix_suggestion(error)}")
        else:
            print(f"  '{line}' -> no error")
        print()

    # Test screen parsing
    print("\nScreen parsing test:")
    print("-" * 50)

    test_screen = [
        "                                        ",
        "10 PRNT \"HELLO\"                        ",
        "                                        ",
        "?SYNTAX ERROR IN 10                     ",
        "                                        ",
        "]                                       ",
    ]

    errors = parse_errors(test_screen)
    print(f"Found {len(errors)} error(s):")
    print(get_error_summary(errors))
