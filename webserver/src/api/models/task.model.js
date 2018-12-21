const mongoose = require('mongoose');
const { QUEUE_PRIORITY_MAX, QUEUE_PRIORITY_MIN, QUEUE_PRIORITY_DEF } = require('./taskQueue.model');

const TaskSchema = new mongoose.Schema({
  schema_version: {
    type: String,
    default: '1',
  },
  test: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'Test',
  },
  start_date: {
    type: Date,
    default: Date.now,
  },
  run_date: {
    type: Date,
    default: Date.now,
  },
  status: {
    type: String,
    default: 'Pending',
  },
  endpoint_list: [String],
  priority: {
    type: Number,
    default: QUEUE_PRIORITY_DEF,
    max: QUEUE_PRIORITY_MAX,
    min: QUEUE_PRIORITY_MIN,
  },
});

const Task = mongoose.model('Task', TaskSchema);
module.exports = Task;
