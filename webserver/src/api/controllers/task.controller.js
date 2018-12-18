const httpStatus = require('http-status');
const { omit } = require('lodash');
const Task = require('../models/task.model');
// const TestResult = require('../models/testResult.model');
// const { handler: errorHandler } = require('../middlewares/error');
const { execFile } = require('child_process');

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

exports.get = async (_, res) => {
  const ret = await Task.get_list();
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

/**
 * Get logged in user info
 * @public
 */
exports.loggedIn = (req, res) => res.json(req.user.transform());

/**
 * Create new user
 * @public
 */
exports.create = async (req, res, next) => {
  try {
    const task = new Task(req.body);
    const savedTask = await task.save();
    res.status(httpStatus.CREATED);
    res.json(savedTask.transform());
  } catch (error) {
    next(Task.checkDuplicateEmail(error));
  }
};

/**
 * Replace existing user
 * @public
 */
exports.replace = async (req, res, next) => {
  try {
    const { user } = req.locals;
    const newUser = new Task(req.body);
    const ommitRole = user.role !== 'admin' ? 'role' : '';
    const newUserObject = omit(newUser.toObject(), '_id', ommitRole);

    await user.update(newUserObject, { override: true, upsert: true });
    const savedUser = await Task.findById(user._id);

    res.json(savedUser.transform());
  } catch (error) {
    next(Task.checkDuplicateEmail(error));
  }
};

/**
 * Update existing user
 * @public
 */
exports.update = (req, res, next) => {
  const ommitRole = req.locals.user.role !== 'admin' ? 'role' : '';
  const updatedUser = omit(req.body, ommitRole);
  const user = Object.assign(req.locals.user, updatedUser);

  user.save()
    .then(savedUser => res.json(savedUser.transform()))
    .catch(e => next(Task.checkDuplicateEmail(e)));
};

/**
 * Get user list
 * @public
 */
exports.list = async (req, res, next) => {
  try {
    const users = await Task.list(req.query);
    const transformedUsers = users.map(user => user.transform());
    res.json(transformedUsers);
  } catch (error) {
    next(error);
  }
};

/**
 * Delete user
 * @public
 */
exports.remove = (req, res, next) => {
  const { user } = req.locals;

  user.remove()
    .then(() => res.status(httpStatus.NO_CONTENT).end())
    .catch(e => next(e));
};
