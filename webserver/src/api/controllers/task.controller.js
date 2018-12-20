// const Task = require('../models/task.model');
const { Test } = require('../models/test.model');
// const TestResult = require('../models/testResult.model');
// const TaskQueue = require('../models/taskQueue.model');
const { execFile } = require('child_process');

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

exports.get = async (_, res) => {
  const ret = await Test.get_list();
  const result = { result: ret };
  return res.send(result);
};

exports.run = async (req, res) => {
  if (req.params.task) {
    execFile(
      'pipenv', ['run', 'tools\\runTest.py', req.params.task],
      { cwd: process.env.ROBOT_SERVER_ROOT },
      (err, stdout) => {
        if (err) {
          // console.error(err);
          console.log(stdout);
          return;
        }
        console.log(stdout);
      },
    );
    await sleep(10);
    return res.status(200).send('12345678');
  }
  return res.sendStatus(404);
};

exports.polling = async (req, res) => {
  if (req.params.task) {
    return res.sendStatus(200);
  }
  return res.sendStatus(404);
};
