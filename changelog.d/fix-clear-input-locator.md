### Fixed

- **`inject clear-input` finds the input box among the background-task panel** (`pd/wake.py`, `supervisor.py`; #1134): the box was taken as the screen's last two rules, so a panel of running tasks under it (with a rule of its own) or a panel that grew or shrank after a press made the box vanish, and clearing stopped after one Ctrl-U. The box is now the last prompt line with a rule above and below it, found again on every read, and the no-break space after the prompt counts as part of the prompt. A box holding two rows is cleared over several presses with the panel below.
