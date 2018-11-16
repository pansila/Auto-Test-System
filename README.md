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

robot starts to connect to client and run the test there