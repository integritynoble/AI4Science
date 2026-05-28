# Releasing pwm-ai4science to PyPI

The package is published to PyPI as **`pwm-ai4science`** (the CLI command
stays `ai4science`). Releases are automated via GitHub Actions + PyPI
Trusted Publishing — no API tokens stored in the repo.

## One-time setup (PyPI Trusted Publishing)

Do this once, before the first release:

1. Log in to <https://pypi.org> with the project owner account.
2. Go to **Your projects → Publishing** (or "Add a pending publisher" if
   the project doesn't exist yet):
   <https://pypi.org/manage/account/publishing/>
3. Add a **GitHub** trusted publisher with:
   - **PyPI Project Name:** `pwm-ai4science`
   - **Owner:** `integritynoble`
   - **Repository:** `AI4Science`
   - **Workflow name:** `publish.yml`
   - **Environment:** `pypi`
4. In the GitHub repo: **Settings → Environments → New environment →**
   name it `pypi` (matches `publish.yml`). Optionally add required
   reviewers so a human approves each publish.

That's it — no secrets to manage. OIDC handles auth at publish time.

## Cutting a release

1. **Bump the version** (single source of truth):
   ```python
   # ai4science/__init__.py
   __version__ = "0.2.0"
   ```
   (`pyproject.toml` reads this via `[tool.setuptools.dynamic]`.)

2. Commit + push:
   ```bash
   git add ai4science/__init__.py
   git commit -m "release: v0.2.0"
   git push origin main
   ```

3. **Create a GitHub Release** with tag `v0.2.0` (Releases → Draft a new
   release → choose/create the tag → Publish). Publishing the release
   triggers `.github/workflows/publish.yml`, which builds, runs
   `twine check`, and publishes to PyPI.

4. Verify:
   ```bash
   pipx install pwm-ai4science        # or: pip install pwm-ai4science
   ai4science version
   ```

## Local build + check (before releasing)

```bash
pip install -e ".[dev]"
python -m build           # writes dist/*.whl + dist/*.tar.gz
twine check dist/*        # must PASS
```

Test the built wheel in a clean environment:
```bash
python3 -m venv /tmp/relcheck
/tmp/relcheck/bin/pip install dist/pwm_ai4science-*.whl
/tmp/relcheck/bin/ai4science version
```

## Manual publish (fallback, if not using the workflow)

```bash
python -m build
twine upload dist/*       # prompts for a PyPI API token
```

## Versioning

Semantic-ish: `MAJOR.MINOR.PATCH`. While pre-1.0, MINOR may include
behavior changes. The version lives only in `ai4science/__init__.py`.
