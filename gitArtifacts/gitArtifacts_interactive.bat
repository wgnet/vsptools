@echo off

pushd %~dp0

call config_venv_py_3_8.bat

py gitArtifacts.py get -i %*

popd
pause
