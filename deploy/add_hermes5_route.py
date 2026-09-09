"""Add only the simulator route to the existing Hermes5 proxy, preserving auth."""
from pathlib import Path
import ast
import sys

path = Path(sys.argv[1])
source = path.read_text()
marker = '    def route(self):\n'
route = '''        if self.path == "/simulator" or self.path.startswith("/simulator/"):
            self.proxy(
                "127.0.0.1", 8010, self.path, PUBLIC_HOST,
                max_body_bytes=40000,
            )
            return
'''
if route in source:
    print("Simulator route already installed")
    sys.exit(0)
if source.count(marker) != 1:
    raise SystemExit("Unexpected proxy source; inspect before installing")
updated = source.replace(marker, marker + route, 1)
ast.parse(updated)
backup = path.with_name(path.name + ".before-task482")
if backup.exists():
    raise SystemExit("Backup already exists; inspect before retrying")
backup.write_text(source)
path.write_text(updated)
print("Simulator route installed; existing routes and authentication preserved")
