const { TaskQueue, QUEUE_PRIORITY_MAX, QUEUE_PRIORITY_MIN } = require('../models/taskQueue.model');

exports.get = async (_, res) => {
  try {
    const queues = await TaskQueue.find({}).exec();
    return res.status(200).send(queues);
  } catch (error) {
    return res.status(404).send({ result: error });
  }
};

exports.post = async (req, res) => {
  console.log(req.body);
  if (req.body) {
    const { endpoint_address: [endpointAddress] } = req.body;
    const works = [];

    // if (tests.length === 0) {
    //   return res.sendStatus(404);
    // }

    // for (let i = 0; i < tests.length; i += 1) {
    //     works.push(Test.findOne({ test_suite: tests[i] }));
    // }
    // try {
    //   const testSuites = await Promise.all(works);
    //   console.log(testSuites);
    // } catch (error) {
    //   console.error(error);
    //   return res.status(404).send({ result: error });
    // }

    try {
      const taskQueue = await TaskQueue.findOne({ endpoint_address: endpointAddress }).exec();
      if (taskQueue) {
        return res.status(404).send({ result: `Task Queue for ${endpointAddress} alread exists` });
      }
    } catch (error) {
      return res.status(404).send({ result: error });
    }

    for (let i = QUEUE_PRIORITY_MIN; i <= QUEUE_PRIORITY_MAX; i += 1) {
      const taskQueue = new TaskQueue({ endpoint_address: endpointAddress, priority: i });
      works.push(taskQueue.save());
    }
    try {
      await Promise.all(works);
    } catch (error) {
      return res.status(404).send({ result: error });
    }

    return res.sendStatus(200);
  }
  return res.status(404).send({ result: 'No content of the request' });
};
