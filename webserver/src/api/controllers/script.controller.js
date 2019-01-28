const tar = require('tar');
const path = require('path');
const fs = require('fs-extra');

const scriptRoot = process.env.ROBOT_SCRIPTS_ROOT;
const tarballTemp = 'temp';

async function makeTarballContent(script) {
  if (!fs.existsSync(path.join(scriptRoot, `${script}.py`))) {
    throw new Error(`${script}.py doesn't exist`);
  }
  try {
    await fs.copy(scriptRoot, tarballTemp, {
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
    return res.sendStatus(404);
  }
};
