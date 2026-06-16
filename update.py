import logging

from src.chat.terminal import run_tui

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)


def main():
    run_tui()


if __name__ == "__main__":
    main()
