from __future__ import annotations

import argparse

from stocktools.infra.paths import Paths
from stocktools.output.display import print_detail
from stocktools.services.config_service import ConfigService


def config_path():
    paths = Paths.resolve()
    paths.init_databases()
    return paths.config_path


def register(subparsers) -> None:
    parser = subparsers.add_parser("config", help="管理配置")
    groups = parser.add_subparsers(dest="config_group", required=True)

    model = groups.add_parser("model", help="管理模型配置")
    actions = model.add_subparsers(dest="model_cmd", required=True)
    set_cmd = actions.add_parser("set", help="写入或覆盖模型配置")
    add_model_args(set_cmd)
    set_cmd.set_defaults(func=handle_model_set)
    show_cmd = actions.add_parser("show", help="查看当前模型配置")
    show_cmd.set_defaults(func=handle_model_show)


def add_model_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--model-name", required=True)


def handle_model_set(args: argparse.Namespace) -> int:
    ConfigService(config_path()).set_model(args.base_url, args.api_key, args.model_name)
    print("模型配置已保存。")
    return 0


def handle_model_show(args: argparse.Namespace) -> int:
    row = ConfigService(config_path()).get_model()
    if row:
        row = dict(row)
        row["api_key"] = "******"
    print_detail(row, "尚未配置模型。")
    return 0
