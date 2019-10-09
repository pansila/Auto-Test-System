@echo off
cd %HOME%
rem Build a certificate signing request and private key.  Use this
rem when your root certificate and key is not available locally.
openssl req -days 3650 -nodes -new -keyout %KEY_DIR%\%1.key -out %KEY_DIR%\%1.csr -config %KEY_CONFIG%
