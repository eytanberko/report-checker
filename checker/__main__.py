"""Allows `python -m checker ...`."""
import sys

from .cli import main

sys.exit(main())
