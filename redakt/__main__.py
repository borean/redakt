import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="redakt",
        description="Redakt -- Local medical document de-identification",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start the HTTP API server instead of the GUI",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="API server host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="API server port (default: 8080)",
    )
    parser.add_argument(
        "--language",
        choices=["tr", "en"],
        default="tr",
        help="Default language for PII detection (default: tr)",
    )

    args = parser.parse_args()

    if args.serve:
        from redakt.api.server import run_server

        run_server(host=args.host, port=args.port, language=args.language)
    else:
        from redakt.app import create_app

        app = create_app(sys.argv)
        sys.exit(app.exec())


if __name__ == "__main__":
    main()
