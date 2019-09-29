@echo off
cd %HOME%
rem Sign a certificate signing request (a .csr file)
rem with a local root certificate and key.

openssl ca -days 3650 -out %KEY_DIR%\%1.crt -in %KEY_DIR%\%1.csr -config %KEY_CONFIG%
