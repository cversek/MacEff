### Fixed

- harness: the child wrapper stamps each start with a date format BSD date accepts; `date -Is` failed on macOS with "invalid argument 's' for -I" (#985).
- harness: the tmux baseline turns on extended keys, so Shift-Tab and other modified keys reach Claude Code in a harness pane (#985).
