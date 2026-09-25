"""Copy standard input to the screen and to a log file (used by the .bat files)."""
import sys

sys.stdin.reconfigure(encoding="utf-8", errors="replace")
sys.stdout.reconfigure(errors="replace")
with open(sys.argv[1], "a", encoding="utf-8", errors="replace") as log:
    for line in sys.stdin:
        sys.stdout.write(line)
        sys.stdout.flush()
        log.write(line)
        log.flush()
