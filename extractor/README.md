# Extractor Tool
Powershell

    (Invoke-WebRequest -Uri https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py -UseBasicParsing).Content | python -

    poetry --version

    poetry build
    poetry install

*(extractor.conf)*

    root: D:\Source\UnrealEngine\4.25.4\
    name: Tracer

    poetry run python extractor.py -n UnrealInsights -t shipping -a
