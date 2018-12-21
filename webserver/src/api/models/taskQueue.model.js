const mongoose = require('mongoose');

const QUEUE_PRIORITY_MAX = 3;
const QUEUE_PRIORITY_MIN = 1;
const QUEUE_PRIORITY_DEF = 2;

// per endpoint per priority queue
const TaskQueueSchema = new mongoose.Schema({
  schema_version: {
    type: String,
    default: '1',
  },
  endpoint_address: {
    type: String,
    required: true,
  },
  priority: {
    type: Number,
    default: QUEUE_PRIORITY_DEF,
    max: QUEUE_PRIORITY_MAX,
    min: QUEUE_PRIORITY_MIN,
  },
  tasks: [{
    type: mongoose.Schema.Types.ObjectId,
    ref: 'Task',
  }],
});

TaskQueueSchema.statics = {
  async push(task, endpointAddress, priority = QUEUE_PRIORITY_DEF) {
    try {
      const queue = await this.findOneAndUpdate(
        { priority, endpoint_address: endpointAddress },
        { $push: { tasks: task } },
        { new: 1 },
      ).exec();
      console.log(queue);
    } catch (error) {
      console.error(error);
    }
  },
};

exports.TaskQueue = mongoose.model('TaskQueue', TaskQueueSchema);
exports.QUEUE_PRIORITY_DEF = QUEUE_PRIORITY_DEF;
exports.QUEUE_PRIORITY_MAX = QUEUE_PRIORITY_MAX;
exports.QUEUE_PRIORITY_MIN = QUEUE_PRIORITY_MIN;
