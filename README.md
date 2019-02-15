- [Introduction](#introduction)
- [Test System Architecture](#test-system-architecture)
- [Design of Robot Test Server](#design-of-robot-test-server)
- [Set up the test environment](#set-up-the-test-environment)
- [Run the test](#run-the-test)
- [Configurations of the auto test system](#configurations-of-the-auto-test-system)
- [How to write a robot test case](#how-to-write-a-robot-test-case)
- [How to write a robot test case in the markdown file](#how-to-write-a-robot-test-case-in-the-markdown-file)
- [How to modify a WiFi Router configurations connected to a SUT](#how-to-modify-a-wifi-router-configurations-connected-to-a-sut)
- [Hacks to the robot](#hacks-to-the-robot)

### Introduction
This is a distributed test system powered by [Robot Framework](https://github.com/robotframework/robotframework) and [Robot Framework Remote Server](https://github.com/robotframework/PythonRemoteServer).
We also use express, a nodejs web framework, to serve the test data/scripts and the Web UI.

### Test System Architecture
A typical architecture for a Robot Remote Server is described in the official [website](https://github.com/robotframework/RemoteInterface).

![](https://i.loli.net/2018/11/28/5bfe0be78657f.jpg)

We improves it by adding a daemon process on the Test Endpoint (aka. Robot Remote Server). The daemon, which is a special test library, will listen on the test endpoint so that it can accept any new test request from the Robot Server without needing to run a corresponding test library every time as we usually do in Robot Remote Server tutorial.

When a test request is sent to the Test Endpoint, a corresponding test library will be downloaded by the daemon process from the Robot Server which is also hosted as a web server. The downloaded test library will be served in the same address where a test library did before, namely we always serve the test libraries at a fixed address.

![](https://i.loli.net/2019/01/25/5c4a65f044250.png)

It's recommended to deploy Robot Server and Test Endpoint on the separated machines. For our case, we use Raspberry Pi 3 to reduce the deployment cost, but more performance PC would work as well.
![](https://i.loli.net/2019/01/24/5c498aa0a7354.png)

### Design of Robot Test Server
![](https://i.loli.net/2019/01/25/5c4a64c32ae53.png)

### Set up the test environment

1. Install python 3.6.x and pip.

2. Install pipenv
   ```bash
   pip install -U pipenv
   ```

3. Set up test endpoint environment
   ```bash
   cd robot-test-endpoint
   pipenv sync
   ```

4. Set up test runner environment
   ```bash
   cd robot-test-runner
   pipenv sync
   pipenv run patch
   ```
   The last step  is to patch robot, details please see sections [How to write a robot test case in the markdown file](#how-to-write-a-robot-test-case-in-the-markdown-file) and [Hacks to the robot](#hacks-to-the-robot).

5. Set up Web server environment

   Web server is powered by `express.js`. Please install [node.js](https://nodejs.org/en/) first. After that, type following commands:
   ```bash
   cd webserver
   npm install -g yarn
   yarn global add yrm
   yrm use cnpm
   yarn
   cp .env.example .env
   ```
   Notice:
   1. All project dependencies will be installed in this step. We use `cnpm` to speed up the package downloading for Chinese user, skip it if you are not.
   2. Please modify `.env` accordingly to suit your case. No changes are needed if you are running all of them in single PC.
   3. Please add yarn binaries path to your `PATH` environment after you've installed yarn, usually it's a path like `C:\Users\<username>\AppData\Local\Yarn\bin\`.

6. Set up the MongoDB database

   1. Install MongoDB from the [official website](https://www.mongodb.com/), please be noted to choose the community version instead of cloud based version.

   2. Build up the test suite database
      ```bash
      cd robot-test-runner
      pipenv run update-db ..\example-test-scripts\robot_tester_scripts
      ```
      It will search all robot scripts under `robot_tester_scripts` and find out all contained robot test suites, markdown is our first-class citizen, it will take precedence if other extension files are present with the same filename.
      It needs to be done only when a test suite is added or modified.

7. The `example-test-scripts` above is just for demonstration so that you can play around with the demo tests out of box. For production environment, you will probably have your own test assets. Same for `robot-test-endpoint`, implement your own work of test endpoint along with the test scripts in a stand-alone repository as they're coupled to work together. Please remember to modify environment variables in the `.env` to point to the right places after setting up your test asset repository.

   By this way you can keep tracking the latest code of auto test framework without the pain of messing with the code here by the frequent changes of test scripts.

### Run the test
1. Run the web server
   ```bash
   cd webserver
   yarn dev
   ```
   Web server will serve Web UI for the auto-test tasks, supply robot scripts with backing python scripts to download, visualize the test results, etc.

2. Run the daemon process of a test endpoint
   ```bash
   cd robot-test-endpoint
   pipenv run daemon
   ```
   It only needs to run only once, following test requests will be intercepted by daemon process to perform the actual tests.

3. Run a test from the test runner folder (can from any PC)

   ```bash
   cd robot-test-runner
   pipenv run start demo-test  # need database updated to work

   # or
   pipenv run robot ..\example-test-scripts\robot_tester_scripts\demo-test.robot
   ```

   Now robot starts to connect to a test endpoint and run the test on that, reports will be generated when test finished under the current directory

4. (Optional) Run a test by the web server API

   To integrate with Web UI, we provide Web API to run the tests. Thereby you can run the tests from any PC that can access web server.
   ```
   http POST http://127.0.0.1/task/run/demo-test

   # or
   curl -d "" http://127.0.0.1/task/run/demo-test
   ```
   Note: `http` is a handy http client tool provided by python, `"pip install httpie"`.

Notice:
1. If you want to run a robot script file written in markdown, please refer to [How to write a robot test case in the markdown file](#how-to-write-a-robot-test-case-in-the-markdown-file) at the end of this document.

2. For a test in action, please check out `wifi-basic-test.md`.

3. The robot server and test endpoint run on the same PC by default, if you want to deploy the them on the different PCs respectively, change the IP addresses in the robot server's config script (`.env`) and test endpoint's config file (`config.yml`). Don't forget to configure the firewall to let through the communication on the TCP port `8270/8271`.

### Configurations of the auto test system
1. Test Runner

   We provide a `config.robot` as a resource file per test suite, supplying configs like desired test endpoint to run the test suite, etc.

2. Test Endpoint

   It's as known as the Robot Remote Server. There is a `config.yml` to describe any SUT dependent details, like serial port interfaces, robot server port, test library serving port, etc.

3. Web server

   All configurations are store in the `.env` file, like mongodb URI, robot scripts root directory, etc.

### How to write a robot test case
Please check out the official [Quick Start Tutorial](https://github.com/robotframework/QuickStartGuide/blob/master/QuickStart.rst) and [User Manuel](http://robotframework.org/robotframework/latest/RobotFrameworkUserGuide.html).

### How to write a robot test case in the markdown file
We patched an unofficial work from [here](https://gist.github.com/Tset-Noitamotua/75d15a2beb9ab6f1931d3871172ebbbf) to make robot support markdown.
After that, robot will read all code blocks in a markdown file with robotframework keyword and execute them.

While we go a bit further by [Adding Support of Tables in Markdown](https://gist.github.com/pansila/8d4f2869ccae891326959c947571ea67). Robot will also read all tables that starts with any robot keyword in a markdown file.

After that, we can execute a test suite in the markdown file as follows.
```bash
robot demo-test.md
```

### How to modify a WiFi Router configurations connected to a SUT
We can accomplish it by using python library `requests` or `beautifulsoup` if the web page is not using any dynamic Web techniques like `PHP`, `JSP` or `ASP`.

Otherwise we can use some crawler techniques here, to this end we need to install [selenium](http://docs.seleniumhq.org/).

These router manipulation scripts are product dependent. At present, we only support a small portion of routers, but they can be easily extended to suit your case.

Especially, we can use a firefox add-on, `Katalon Recorder`, which could record your operations on the web page and produce corresponding python code, we can in turn adapt the resultant code into our test scripts.

### Hacks to the robot
1. robot will cache test libraries if they have been imported before, we disabled it in _import_library in venv/lib/site-packages/robot/running/importer.py to support reloading test libraries in order to get the latest test library downloaded by daemon process on the test endpoint.
