@echo off

pushd %~dp0

call config_venv_py_3_8.bat

py -m pip install -r requirements.txt -q ^
  --no-warn-script-location --disable-pip-version-check ^
  --trusted-host artifactory.geoproxy.iv ^
  --index-url http://artifactory.geoproxy.iv/artifactory/api/pypi/vsp-pypi/simple

py gitArtifacts.py %*

popd
