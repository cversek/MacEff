### Removed

- **The unused `_MODEL_CONTEXT_MAP` in `utils/tokens.py`** (#860 item 8): a table of four model names and window sizes that nothing read. The window comes from `MACF_CONTEXT_WINDOW`, the project config, or the 200k default, and the hook readout says when it is the assumed default; a dead table beside that chain suggested the model name chose the window, which it does not.
