import sys
try:
    x = 1/0
except (ZeroDivisionError, ValueError) as e:
    print(f"⚠️ MACF: math error: {e}", file=sys.stderr)
