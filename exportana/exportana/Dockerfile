FROM artifactory.geoproxy.iv:8081/vsp-docker/tools/python:3.8

ENV VENV_PATH="/code/poetry/.venv" \
    POETRY_HOME="/code/poetry" \
    EXPORTANA_PATH="/code/exportana" \
    PIP_DISABLE_PIP_VERSION_CHECK=on

RUN mkdir -p $POETRY_HOME/installation_scripts \
    && curl -o $POETRY_HOME/installation_scripts/get-poetry.py \
      http://artifactory.geoproxy.iv/artifactory/vsp-rpm/poetry/get-poetry.py \
    && curl -o $POETRY_HOME/installation_scripts/poetry.tar.gz \
      http://artifactory.geoproxy.iv/artifactory/vsp-rpm/poetry/1.1.13/poetry-1.1.13-linux.tar.gz \
    && python $POETRY_HOME/installation_scripts/get-poetry.py -y \
    --file $POETRY_HOME/installation_scripts/poetry.tar.gz

ENV PATH="$POETRY_HOME/bin:$VENV_PATH/bin:$PATH"

RUN groupadd exportana_user -g 1000 && useradd exportana_user -m -u 1000 -g 1000

COPY . $EXPORTANA_PATH

RUN chown -R exportana_user:exportana_user /code
USER exportana_user:exportana_user

WORKDIR $EXPORTANA_PATH

RUN poetry config virtualenvs.path $VENV_PATH
RUN poetry build -f wheel
RUN poetry install

ENTRYPOINT ["poetry", "run", "exportana"]
