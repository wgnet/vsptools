import json


def read_config(path):
    with open(path, "r") as file:
        config: dict = json.load(file)
        return config
