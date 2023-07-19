@echo off
pip install twine
twine upload --config-file .pypirc dist/* -r vsppypi
