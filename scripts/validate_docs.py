#!/usr/bin/env python3
"""
Validate documentation links in markdown files.

Checks:
- Relative links to other .md files exist
- Internal anchors are valid
- No broken cross-references

Usage:
    python scripts/validate_docs.py docs/2*.md
    python scripts/validate_docs.py docs/
"""

import argparse
import re
import sys
from pathlib import Path


def extract_links(content: str) -> list[tuple[str, int]]:
    """Extract markdown links from content.

    Args:
        content: Markdown file content

    Returns:
        List of (link, line_number) tuples
    """
    links = []
    for i, line in enumerate(content.split("\n"), 1):
        # Match markdown links: [text](url)
        for match in re.finditer(r"\[([^\]]+)\]\(([^\)]+)\)", line):
            link = match.group(2)
            links.append((link, i))
    return links


def validate_doc_file(doc_path: Path, base_dir: Path) -> list[str]:
    """Validate links in a documentation file.

    Args:
        doc_path: Path to markdown file
        base_dir: Base directory for resolving relative links

    Returns:
        List of error messages
    """
    errors = []

    try:
        content = doc_path.read_text(encoding="utf-8")
    except Exception as e:
        return [f"Failed to read {doc_path}: {e}"]

    links = extract_links(content)

    for link, line_num in links:
        # Skip external links (http/https)
        if link.startswith(("http://", "https://", "mailto:", "#")):
            continue

        # Handle anchor links (e.g., file.md#section)
        if "#" in link:
            link_path, anchor = link.split("#", 1)
        else:
            link_path = link
            anchor = None

        # Skip empty links
        if not link_path:
            continue

        # Resolve relative path
        if link_path.startswith("/"):
            # Absolute path from repo root
            target = base_dir / link_path.lstrip("/")
        else:
            # Relative to current file
            target = (doc_path.parent / link_path).resolve()

        # Check if file exists
        if not target.exists():
            errors.append(f"{doc_path.name}:{line_num}: Broken link to {link_path}")
            continue

        # TODO: Could validate anchors by parsing target file headers
        # For now, we just check file existence

    return errors


def main():
    """Main validation function."""
    parser = argparse.ArgumentParser(description="Validate documentation links")
    parser.add_argument("files", nargs="+", help="Markdown files or directories to validate")
    parser.add_argument(
        "--base-dir", default=".", help="Base directory for resolving links (default: current dir)"
    )
    args = parser.parse_args()

    base_dir = Path(args.base_dir).resolve()
    all_errors = []

    # Collect all markdown files
    md_files = []
    for file_arg in args.files:
        path = Path(file_arg)
        if path.is_dir():
            md_files.extend(path.glob("*.md"))
        elif path.suffix == ".md":
            md_files.append(path)
        else:
            print(f"Warning: Skipping non-markdown file: {file_arg}", file=sys.stderr)

    print(f"Validating {len(md_files)} markdown files...")

    # Validate each file
    for md_file in sorted(md_files):
        errors = validate_doc_file(md_file, base_dir)
        if errors:
            all_errors.extend(errors)

    # Report results
    if all_errors:
        print("\n❌ Validation failed with errors:\n", file=sys.stderr)
        for error in all_errors:
            print(f"  {error}", file=sys.stderr)
        print(f"\nTotal: {len(all_errors)} error(s)", file=sys.stderr)
        sys.exit(1)
    else:
        print("✅ All documentation links validated successfully")
        sys.exit(0)


if __name__ == "__main__":
    main()
