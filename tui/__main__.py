"""
CLI entrypoint for running Darwin Trader TUI via `python -m tui`.
"""
from tui.app import DarwinTraderApp


def main() -> None:
    app = DarwinTraderApp()
    app.run()


if __name__ == "__main__":
    main()
