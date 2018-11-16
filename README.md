### Set up the test environment

1. Install virtualenv
```dos
pip install -U virtualenv
```

2. Set up client environment
```dos
cd robotclient
virtualenv --no-site-packages venv
venv\scripts\active.bat
pip install -r requirements.txt
```
3. Set up server environment
```dos
cd robotserver
virtualenv --no-site-packages venv
venv\scripts\active.bat
pip install -r requirements.txt
```
### Run the test
1. Run the agent of a client
```dos
cd robotclient
venv\scripts\active.bat
python agent.py
```
robot remote server starts to listen now.

2. Run a test from the server
```dos
cd robotserver
venv\scripts\active.bat
cd iperf-test
robot wifi-basic-test.robot
```

Now robot starts to connect to client and run the test on the client, reports will be generated when test finished under the server's test directory

The server and client of demo run on the same local PC, if you want to deploy the them on the different PCs, change the IP addresses in the server's robot test script and client's endpoint config file. Don't forget to configure the firewall to let pass the communication on the TCP port 8270/8271.