# Build & Publish Instruction

prepare virtual env.

```shell
# make venv
# TODO

# install packages
pip install twine
```

Build package

```shell
setup.py sdist bdist_wheel
twine check dist/*
```

Upload to registry

```shell
twine upload --repository-url https://local/artifactory/api/pypi/vsp-pypi-local dist/*
```
