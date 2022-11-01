# metrics-render

HTTP service that rendering promql into image, support alerting rules expression

## Installation

```shell
$ pip install metrics-render
```

## Run

```shell
# Change your config content
$ metrics-render serve --config-path ./example-config.json
```

From this URL, you can get the result image of PromQL query:

```
http://127.0.0.1:8080/render?ds_name<ds-name>&expr=<Prometheus query>&starttime=1666860113&endtime=1666863695
```
