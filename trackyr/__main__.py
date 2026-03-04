"""Entry point: python -m trackyr"""

from trackyr.app import Trackyr


def main() -> None:
    app = Trackyr()
    app.run()


if __name__ == "__main__":
    main()
