from app.env import load_env

load_env()

from gauntlet.cli import cli  # noqa: E402

cli()
