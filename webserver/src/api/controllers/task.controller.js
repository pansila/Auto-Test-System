const Task = require('../models/task.model');
const Test = require('../models/test.model');
// const TestResult = require('../models/testResult.model');
const { TaskQueue } = require('../models/taskQueue.model');
// const { execFile } = require('child_process');

exports.get = async (_, res) => {
  const ret = await Test.get_list();
  const result = { result: ret };
  return res.send(result);
};

exports.run = async (req, res) => {
  if (req.params.task) {
    try {
      const test = await Test.findOne({ test_suite: req.params.task }).exec();
      console.log(test);
      req.body.test = test._id;
      console.log(req.body);
      const task = new Task(req.body);
      const savedTask = await task.save();
      console.log(savedTask);
      TaskQueue.push(savedTask, '192.168.3.100:8270');
      return res.status(200).send(savedTask.id);
    } catch (error) {
      console.error(error);
      return res.sendStatus(404);
    }
    // execFile(
    //   'pipenv', ['run', 'tools\\runTest.py', req.params.task],
    //   { cwd: process.env.ROBOT_SERVER_ROOT },
    //   (err, stdout) => {
    //     if (err) {
    //       // console.error(err);
    //       console.log(stdout);
    //       return;
    //     }
    //     console.log(stdout);
    //   },
    // );
  }
  return res.sendStatus(404);
};

exports.polling = async (req, res) => {
  if (req.params.task) {
    return res.sendStatus(200);
  }
  return res.sendStatus(404);
};
