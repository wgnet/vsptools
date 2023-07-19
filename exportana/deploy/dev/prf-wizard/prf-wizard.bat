@echo off

if exist .venv goto launch

py -m pip install virtualenv==20.4.2 ^
  --no-warn-script-location --disable-pip-version-check ^
  --trusted-host artifactory.geoproxy.iv ^
  --index-url http://artifactory.geoproxy.iv/artifactory/api/pypi/vsp-pypi/simple

py -m virtualenv .venv

.venv\Scripts\pip install -r requirements.txt -q ^
  --no-warn-script-location --disable-pip-version-check ^
  --trusted-host artifactory.geoproxy.iv ^
  --index-url http://artifactory.geoproxy.iv/artifactory/api/pypi/vsp-pypi/simple

:launch

.venv\Scripts\python.exe prf-wizard.py %*

pause
