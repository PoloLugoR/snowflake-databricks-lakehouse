import sys
from pathlib import Path

# The script lives in python/ (not a package), so make it importable for the tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))