import sys


def main():
    from qwenkk.app import create_app

    app = create_app(sys.argv)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
