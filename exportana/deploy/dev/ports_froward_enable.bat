@echo off

set ports=9200 5050

(for %%p in (%ports%) do (
    echo #==============================#
    echo Setting up '%%p' port
    echo #==============================#
    netsh interface portproxy add v4tov4 listenport=%%p listenaddress=0.0.0.0 connectport=%%p connectaddress=127.0.0.1
    netsh interface portproxy add v4tov6 listenaddress=0.0.0.0 listenport=%%p connectaddress=::1 connectport=%%p protocol=tcp
    netsh advfirewall firewall add rule name=exportana_%%p dir=in action=allow protocol=TCP localport=%%p
    echo #------------------------------#
    echo.
))

netsh interface portproxy dump
@pause