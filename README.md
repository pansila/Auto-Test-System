- [Introduction](#introduction)
- [Test System Architecture](#test-system-architecture)
- [Set up the test environment](#set-up-the-test-environment)
- [Run the test](#run-the-test)
- [Configuration of the test system](#configuration-of-the-test-system)
- [How to write a robot test case](#how-to-write-a-robot-test-case)
- [How to write a robot test case in the markdown file](#how-to-write-a-robot-test-case-in-the-markdown-file)
- [Hacks to the robot](#hacks-to-the-robot)

### Introduction
This is a distributed test system powered by [Robot Framework](https://github.com/robotframework/robotframework) and [Robot Framework Remote Server](https://github.com/robotframework/PythonRemoteServer).
We also use express, a nodejs web framework, to serve the test data/scripts and the Web UI.

### Test System Architecture
This is the typical architecture for a remote server.

![](https://i.loli.net/2018/11/28/5bfe0be78657f.jpg)

We improved it by adding an agent, which is a special test library, to listen in the remote server which then could accept any new test request from the test server. In this manner, we don't need to start the remote server at a different address to serve the corresponding test library.

When a test request is issued to the remote server, a corresponding test library will be downloaded by the agent daemon from the test server which is also hosted as a web server. The downloaded test library will be served in the same address as where a test library served before, namely we always serve the test libraries at a fixed address.

Need a picture here!!!

### Set up the test environment

1. Install virtualenv
```dos
pip install -U virtualenv
```

2. Set up test client environment
```dos
cd robotclient
virtualenv --no-site-packages venv
venv\scripts\active.bat
pip install -r requirements.txt
```
3. Set up test server environment
```dos
cd robotserver
virtualenv --no-site-packages venv
venv\scripts\active.bat
pip install -r requirements.txt
```
4. Set up web server environment
Web server is running by express. Need to install [node.js](https://nodejs.org/en/) first.
Then:
```dos
cd webserver
npm install -g yarn
yarn global add yrm
yrm use cnpm
yarn
```
All project dependent packages will be installed in this step. We use `cnpm` to speed up the package downloading.

### Run the test
1. Run the web server
```dos
cd webserver
yarn dev
```

2. Run the agent of a client
```dos
cd robotclient
venv\scripts\active.bat
python agent.py
```
robot remote server starts to listen now.

3. Run a test from the server
```dos
cd robotserver
venv\scripts\active.bat
cd iperf-test
robot wifi-basic-test.robot
```

Now robot starts to connect to client and run the test on the client, reports will be generated when test finished under the server's test directory

The server and client of demo run on the same local PC, if you want to deploy the them on the different PCs, change the IP addresses in the server's robot test script and client's endpoint config file. Don't forget to configure the firewall to let pass the communication on the TCP port 8270/8271.

### Configuration of the test system
1. On the test server side, we provide a config.robot as a resource file per test suite, supplying desired remote server to execute the test suite, etc.
2. On the remote server side, we provide a config.yml to describe any SUT dependent details, like serial port interfaces, remote server port, test library serving port, etc.

### How to write a robot test case
Please check out the [official user manuel](http://robotframework.org/robotframework/latest/RobotFrameworkUserGuide.html).

### How to write a robot test case in the markdown file
We patched an unofficial work from [here](https://gist.github.com/Tset-Noitamotua/75d15a2beb9ab6f1931d3871172ebbbf) to make robot support markdown.
After that, robot will read all code blocks in a markdown file with robotframework keyword and execute them. 

And we go a bit further by [adding support of tables in markdown](https://gist.github.com/pansila/8d4f2869ccae891326959c947571ea67). Robot will also read all tables that starts with any robot keyword in a markdown file.

After that, we can execute a test suite in the markdown file as follows.
```dos
robot wifi-basic-test.md
```

An example to start with is wifi-basic-test.md in the wifi-basic-test folder.

### Hacks to the robot
1. robot will cache test libraries if they have been imported before, we disabled it in _import_library in venv/lib/site-packages/robot/running/importer.py to support reloading test libraries in order to get the latest test library downloaded by [test agent]()