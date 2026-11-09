"""Build sketches without the GUI:  python main.py [project.json] [--board esp32] [--out dir]"""

import sys

from embedco.cli import build_main

if __name__ == "__main__":
    sys.exit(build_main())
