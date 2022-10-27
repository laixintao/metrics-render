import os
import logging
import minio
import hashlib
from plotly.subplots import make_subplots
import requests
from pathlib import Path
from time import time
from datetime import datetime
from metrics_render.config import load_config
from typing import List, Dict, Tuple
from promqlpy import split_binary_op
import plotly.graph_objects as go
from minio import Minio


logger = logging.getLogger(__name__)


class MetricsRender:
    def __init__(self, config_path) -> None:
        self.global_config = load_config(config_path)
        self.image_path = Path(self.global_config["image_path"])
        if not self.image_path.exists():
            logger.info(f"Image path {self.image_path} not exist, creating...")
            self.image_path.mkdir(parents=True, exist_ok=True)
        self.minio = Minio(
            self.global_config["s3_domain"],
            access_key=self.global_config["s3_access_key"],
            secret_key=self.global_config["s3_secret"],
        )
        self.bucket = self.global_config["s3_bucket"]
        self.image_prefix = self.global_config["s3_image_prefix"]

    def get_s3_image(self, name):
        try:
            response = self.minio.get_object(self.bucket, f"{self.image_prefix}/{name}")
        except minio.error.S3Error as e:
            if e.code == "NoSuchKey":
                return None
            raise
        data = response.read()
        response.close()
        return data

    def upload_s3_image(self, image):
        self.minio.fput_object(
            self.bucket,
            f"{self.image_prefix}/{image}",
            image,
            content_type="application/csv",
        )

    def render(self, ds_url, compare_expr, starttime, endtime):
        render_image_name = MetricsRender.image_name_hash(
            ds_url, compare_expr, starttime, endtime
        )
        logger.info(
            f"Render {ds_url=} {compare_expr=} {starttime=} {endtime=}, computed_hash ="
            f" {render_image_name}"
        )

        image = self.get_s3_image(render_image_name)

        if image:
            logger.info(f"Got file from s3 bucket: {render_image_name}")
            return image

        all_conditions = MetricsRender.parse_to_pairs(compare_expr)
        subplots = len(all_conditions)
        logger.info(f"Split {compare_expr=} to {all_conditions=}")

        fig = make_subplots(
            cols=1,
            rows=len(all_conditions),
            subplot_titles=[c[2] for c in all_conditions],
        )
        for index, condition in enumerate(all_conditions):
            self.render_one_comparison(
                fig,
                index,
                ds_url,
                condition[0],
                condition[1],
                starttime,
                endtime,
            )

        start_date = datetime.fromtimestamp(starttime).strftime("%Y-%m-%d")
        fig.update_layout(
            title_text=f"{start_date} dashboard",
            height=500 * subplots,
            width=800,
        )

        _t1 = time()
        fig.write_image(render_image_name)
        logger.info(f"Plotly render to file {render_image_name}, took {time() - _t1}s")
        self.upload_s3_image(render_image_name)
        with open(render_image_name, "br") as f:
            content = f.read()

        os.remove(render_image_name)
        return content

    @staticmethod
    def image_name_hash(*args):
        hash_object = hashlib.sha1("/".join([str(x) for x in args]).encode())
        hex_str = hash_object.hexdigest()
        return f"{hex_str}.png"

    @staticmethod
    def parse_to_pairs(compare_expr) -> List[Tuple]:
        grammar = split_binary_op(compare_expr)
        if grammar["op"] in ["and", "or", "unless"]:
            return MetricsRender.parse_to_pairs(
                grammar["left"]["code"]
            ) + MetricsRender.parse_to_pairs(grammar["right"]["code"])
        return [(grammar["left"]["code"], grammar["right"]["code"], grammar["code"])]

    def render_one_comparison(
        self, fig, index, ds_url, expr_data, expr_threshold, starttime, endtime
    ):
        logger.debug(f"Query metrics data... {expr_data=}")
        metrics_data = self.query_range(ds_url, expr_data, starttime, endtime)

        metrics_data_list: List[Dict] = metrics_data["data"]["result"]
        logger.debug(f"Query metrics data... {metrics_data_list=}")

        logger.debug(f"Query metrics threshold... {expr_threshold=}")
        metrics_threshold = self.query_range(ds_url, expr_threshold, starttime, endtime)

        metrics_threshold_list: List[Dict] = metrics_threshold["data"]["result"]
        logger.debug(f"Query metrics threshold... {metrics_threshold_list=}")

        picture = self.draw(fig, index, metrics_data_list, metrics_threshold_list)

        return picture

    def draw(self, fig, index, metrics, thresholds):
        for metric in metrics:
            self._add_trace(fig, index, metric, dict(), name=None)
        for threshold in thresholds:
            self._add_trace(
                fig,
                index,
                threshold,
                dict(color="firebrick", width=4, dash="dash"),
                name="threshold",
            )

    def _add_trace(self, fig, index, metric, line_config, name=None):
        value_pairs = metric["values"]
        x = []
        y = []
        for pair in value_pairs:
            logger.debug(f"{pair=}")
            _x = datetime.fromtimestamp(pair[0]).strftime("%H:%M")
            _y = float(pair[1])
            x.append(_x)
            y.append(_y)

        labels = metric["metric"]
        if name is None:
            name = " ".join(f"{k}={v}" for k, v in labels.items())
        logger.debug(f"add one trace, {x=}, {y=}")
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                name=name,
                line=line_config,
            ),
            col=1,
            row=1 + index,
        )

    def render_named_ds(self, ds_name, expr, starttime, endtime):
        ds_url = self.global_config["prom_named_datasources"][ds_name]
        return self.render(ds_url, expr, starttime, endtime)

    def query_range(self, ds_url, expr, starttime, endtime):
        logger.debug(f"Query Prometheus {expr=}")
        payload = {
            "query": expr,
            "start": starttime,
            "end": endtime,
            "step": "15s",
        }
        resp = requests.get(f"{ds_url}/api/v1/query_range", params=payload)
        logger.debug(f"Get resp from prometheus: {resp.text=}")
        return resp.json()


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.DEBUG,
        format="[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(stream=sys.stdout)],
    )
    MetricsRender("./example-config.json").render_named_ds(
        "universal",
        'count(up{job="node"}==0) by (tag_idc) > 20 and count(up{job="node",'
        ' tag_idc="sg10"}==0) by (tag_idc) < 1',
        1666860113,
        1666863695,
    )
