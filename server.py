"""Start the EmbedCo editor:  python server.py [--port 9000] [--no-browser]"""

import sys

from embedco.cli import serve_main

if __name__ == "__main__":
    sys.exit(serve_main())
