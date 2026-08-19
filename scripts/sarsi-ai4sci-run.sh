#!/usr/bin/env bash
# Launch the ai4science ACP adapter for the sarsi account.
#
# stdout is the ACP wire. Nothing but protocol traffic may go to it.
set -u

# The adapter module lives in the promoted tree; the ENGINE — where the
# `ai4sci` mode lives — is a worktree of the same clone on the rename branch.
# They are separate on purpose: running the engine out of the adapter tree
# resolves the mode to a fallback and fails for a reason that has nothing to
# do with the adapter.
export PYTHONPATH="/home/sarsi/pwm/AI4Science-acp${PYTHONPATH:+:$PYTHONPATH}"
export AI4SCI_ACP_ENGINE_PATH="/home/sarsi/pwm/AI4Science-engine"
export AI4SCI_ACP_RECORDS="${AI4SCI_ACP_RECORDS:-/home/sarsi/.openclaw/acpx/ai4sci-records}"

# An executor must be able to write; the package default is read-only, and the
# choice belongs here where it is visible rather than inside the adapter.
export AI4SCI_ACP_READ_ONLY=0

# Move to a neutral directory so Python's "" sys.path entry (cwd) cannot
# shadow ai4science with a package that lives in the gateway's working dir.
cd /tmp

# The shared dependency venv. The package itself comes from PYTHONPATH above,
# so this interpreter supplies numpy/scipy/typer and nothing of ai4science.
exec /opt/pwm/venvs/ai4sci/bin/python -m ai4science.harness.acp "$@"
