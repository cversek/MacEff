
## FP: ~/.local/bin not on PATH (Cycle 42)

**Symptom**: pip-installed scripts require full path
```
> neurovep_process --help
/bin/bash: line 1: neurovep_process: command not found
```

**Root Cause**: `~/.bash_init.sh` doesn't add `~/.local/bin` to PATH

**Fix**: Add to create_bash_init():
```bash
export PATH="$HOME/.local/bin:$PATH"
```

---

## FP: conda env not activating (Cycle 42)

**Symptom**: `conda env list` shows no active environment in non-interactive shell

**Root Cause**: `MACEFF_CONDA_ENV` not set, so conditional activation never triggers

**Fix**: Set default conda env from agents.yaml or hardcode neurovep_data activation

