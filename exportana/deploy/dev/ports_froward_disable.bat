@echo off

set ports=9200 5050

(for %%p in (%ports%) do (
    echo #==============================#
    echo Removing info about '%%p' port
    echo #==============================#
    netsh interface portproxy delete v4tov4 listenport=%%p listenaddress=0.0.0.0
    netsh interface portproxy delete v4tov6 listenaddress=0.0.0.0 listenport=%%p
    netsh advfirewall firewall delete rule name=exportana_%%p
    echo #------------------------------#
    echo.
))

netsh interface portproxy dump
@pause
