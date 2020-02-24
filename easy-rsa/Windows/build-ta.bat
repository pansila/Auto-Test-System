@echo off
cd %HOME%
rem Using tls-auth requires that you generate a shared-secret key
rem that is used in addition to the standard RSA certificate/key
rem This key should be copied over a pre-existing secure channel to
rem the server and all client machines. It can be placed in the same
rem directory as the RSA .key and .crt files.
openvpn --genkey --secret %KEY_DIR%\ta.key
