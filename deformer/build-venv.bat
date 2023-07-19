@echo off

set ROOT_DIR=%~dp0
py -m venv %ROOT_DIR%.venv
copy /y pip.ini .venv\
call "%ROOT_DIR%.venv\Scripts\activate.bat"
python -m pip install --upgrade pip==22.3 setuptools==61.0
pip install --editable .
