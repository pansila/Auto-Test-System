const httpStatus = require('http-status');
const { omit } = require('lodash');
const User = require('../models/user.model');
// const { handler: errorHandler } = require('../middlewares/error');
const tar = require('tar');
const path = require('path');
const fs = require('fs-extra');

const scriptRoot = process.env.ROBOT_SCRIPTS_ROOT;
const tarballTemp = 'temp';
const dependency = [/customtestlibs[/\\]?.*/];

async function makeTarballContent(script) {
  if (!fs.existsSync(path.join(scriptRoot, `${script}.py`))) {
    throw new Error(`${script}.py doesn't exist`);
  }
  try {
    await fs.copy(scriptRoot, tarballTemp, {
      filter: (file) => {
        // console.log(file);
        if (file.endsWith(scriptRoot)) {
          return true;
        }
        for (let i = 0; i < dependency.length; i += 1) {
          if (dependency[i].test(file)) return true;
        }
        if (file.endsWith(`${script}.py`)) {
          return true;
        }
        return false;
      },
      preserveTimestamps: true,
    });
  } catch (error) {
    console.error(error);
  }
}

async function packScript(script) {
  const output = `${script}.tgz`;

  await fs.emptyDir(tarballTemp);
  await makeTarballContent(script);
  await tar.create(
    {
      gzip: true,
      file: output,
    },
    [tarballTemp],
  );

  return output;
}

exports.get = async (req, res) => {
  let { script } = req.params;
  if (script.endsWith('.py')) {
    script = script.slice(0, -3);
  }
  try {
    const scriptTar = await packScript(script);
    return res.sendFile(scriptTar, {
      root: process.cwd(),
    }, (err) => {
      if (err) console.error(err);
    });
  } catch (err) {
    console.error(err);
    res.send(404);
  }
  return undefined; // make eslint happy
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
    const user = new User(req.body);
    const savedUser = await user.save();
    res.status(httpStatus.CREATED);
    res.json(savedUser.transform());
  } catch (error) {
    next(User.checkDuplicateEmail(error));
  }
};

/**
 * Replace existing user
 * @public
 */
exports.replace = async (req, res, next) => {
  try {
    const { user } = req.locals;
    const newUser = new User(req.body);
    const ommitRole = user.role !== 'admin' ? 'role' : '';
    const newUserObject = omit(newUser.toObject(), '_id', ommitRole);

    await user.update(newUserObject, { override: true, upsert: true });
    const savedUser = await User.findById(user._id);

    res.json(savedUser.transform());
  } catch (error) {
    next(User.checkDuplicateEmail(error));
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
    .catch(e => next(User.checkDuplicateEmail(e)));
};

/**
 * Get user list
 * @public
 */
exports.list = async (req, res, next) => {
  try {
    const users = await User.list(req.query);
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
