- [Introduction](#introduction)
- [Test System Architecture](#test-system-architecture)
- [Set up the test environment](#set-up-the-test-environment)
- [Run the test](#run-the-test)
- [Configurations of the auto test system](#configurations-of-the-auto-test-system)
- [How to write a robot test case](#how-to-write-a-robot-test-case)
- [How to write a robot test case in the markdown file](#how-to-write-a-robot-test-case-in-the-markdown-file)
- [How to modify router configurations](#how-to-modify-router-configurations)
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

1. Install pipenv
   ```dos
   pip install -U pipenv
   ```

2. Set up test client environment
   ```dos
   cd robotclient
   pipenv install
   ```

3. Set up test server environment
   ```dos
   cd robotserver
   pipenv install
   ```

4. Set up web server environment

   Web server is running by express. Need to install [node.js](https://nodejs.org/en/) first. Then:
   ```dos
   cd webserver
   npm install -g yarn
   yarn global add yrm
   yrm use cnpm
   yarn
   cp .env.example .env
   ```
   All project dependent packages will be installed in this step. We use `cnpm` to speed up the package downloading.

5. Set up the MongoDB database

   Install mongodb from the [official website](https://www.mongodb.com/)


### Run the test
1. Run the web server
   ```dos
   cd webserver
   yarn dev
   ```

2. Run the agent of a client
   ```dos
   cd robotclient
   pipenv run agent.py
   ```
   robot remote server starts to listen now.

3. Build up the test suite database
   ```dos
   cd robotserver
   pipenv run tools\getTest.py robot_scripts
   ```
   It needs to be done only when new test suite is added.

4. Run a test from the server (actually it can be any remote PC)

   ```dos
   cd robotserver
   tools\runTest.py demo-test
   
   # or you can do it the vanilla way
   cd robotserver\robot_scripts\demo
   pipenv run robot demo-test.robot
   
   # or
   pipenv shell
   cd robotserver\robot_scripts\demo
   robot demo-test.robot
   ```

   Now robot starts to connect to client and run the test on the client, reports will be generated when test finished under the server's test directory

Notice:
1. If you want to run a robot script file written in markdown, please refer to [How to write a robot test case in the markdown file](#how-to-write-a-robot-test-case-in-the-markdown-file) at the end of this document.

2. For a test in action, please check out `wifi-basic-test.md` in `the wifi-basic-test` folder.

3. The server and client of demo run on the same PC, if you want to deploy the them on the different PCs respectively, change the IP addresses in the test server's robot test script and test client's endpoint config file. Don't forget to configure the firewall to let pass the communication on the TCP port 8270/8271.

### Configurations of the auto test system
1. Test Server

   We provide a config.robot as a resource file per test suite, supplying configs like desired remote server to execute the test suite, etc.

2. Test Client

   Ther is a config.yml to describe any SUT dependent details, like serial port interfaces, test server port, test library serving port, etc.

3. Web server

   All configurations are store in the .env file, there are like mongodb URI, robot scripts root directory, etc.

### How to write a robot test case
Please check out the [official user manuel](http://robotframework.org/robotframework/latest/RobotFrameworkUserGuide.html).

### How to write a robot test case in the markdown file
We patched an unofficial work from [here](https://gist.github.com/Tset-Noitamotua/75d15a2beb9ab6f1931d3871172ebbbf) to make robot support markdown.
After that, robot will read all code blocks in a markdown file with robotframework keyword and execute them. 

And we go a bit further by [adding support of tables in markdown](https://gist.github.com/pansila/8d4f2869ccae891326959c947571ea67). Robot will also read all tables that starts with any robot keyword in a markdown file.

After that, we can execute a test suite in the markdown file as follows.
```dos
robot demo-test.md
```

### How to modify router configurations
We can use some crawler techniques here, thus we need to install [selenium](http://docs.seleniumhq.org/).

These router manipulation scripts are product dependent. At present, we only support a small portion of routers, but they can be easily extended to suit your case.

Especially, we can use a firefox add-on, Katalon Recorder, which could record your operations on the web page and produce corresponding python code, we can in turn adapt the resultant code into our test scripts.

### Hacks to the robot
1. robot will cache test libraries if they have been imported before, we disabled it in _import_library in venv/lib/site-packages/robot/running/importer.py to support reloading test libraries in order to get the latest test library downloaded by [test agent]() on test client.
