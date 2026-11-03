"""Static assets and banks shipped in the wheel (SP-PACKAGING).

This package has no code. `pyproject.toml` maps `sparring_data.app` to `app/` and `sparring_data.bank` to `bank/`
at the repository root, so an installed Sparring finds the web page and the banks with
`importlib.resources.files("sparring_data")`. In a clone, `backend/paths.py` uses the directories next to
`server.py` and never looks here.
"""
