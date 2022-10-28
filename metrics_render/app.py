import sys
import click
import logging
from flask import Flask, make_response, request
import waitress

from metrics_render.metrics_render import MetricsRender


def create_app(config_path):
    app = Flask(
        __name__,
    )
    metricsrender = MetricsRender(config_path)
    config_log(logging.DEBUG)

    @app.route("/ping")
    def ping():
        return "pong"

    @app.route("/render")
    def render():
        args = request.args
        image = metricsrender.render_named_ds(
            ds_name=args["ds_name"],
            expr=args["expr"],
            starttime=int(args["starttime"]),
            endtime=int(args["endtime"]),
        )

        response = make_response(image)
        response.headers.set("Content-Type", "image/png")

        return response

    return app


def config_log(level):
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(stream=sys.stdout)],
    )


@click.group()
@click.option(
    "--log-level",
    default=20,
    help=(
        "Python logging level, default 20, can set from 0 to 50, step 10:"
        " https://docs.python.org/3/library/logging.html"
    ),
)
def main(log_level):
    config_log(log_level)


@main.command(help="Start a HTTP_SD server for Prometheus.")
@click.option("--host", "-h", default="127.0.0.1", help="The interface to bind to.")
@click.option("--port", "-p", default=8080, help="The port to bind to.")
@click.option("--connection-limit", "-c", default=1000, help="Server connection limit")
@click.option("--threads", "-t", default=64, help="Server threads")
@click.option(
    "--config-path",
    required=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
)
def serve(host, port, connection_limit, threads, config_path):
    app = create_app(config_path)
    waitress.serve(
        app,
        host=host,
        port=port,
        connection_limit=connection_limit,
        threads=threads,
    )
