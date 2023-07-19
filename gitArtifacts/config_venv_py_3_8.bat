@echo off

set args=%*

echo Installing deps...

pushd "%~dp0../.."

py -3.8 -m venv .venv
call .venv\Scripts\activate.bat

popd

if "%1"=="" goto :end

py -m pip install %args%^
 --disable-pip-version-check^
 --no-warn-script-location^
 --trusted-host artifactory.geoproxy.iv^
 --index-url http://artifactory.geoproxy.iv/artifactory/api/pypi/vsp-pypi/simple

:end


