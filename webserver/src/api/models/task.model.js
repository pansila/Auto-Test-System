const mongoose = require('mongoose');
const { TestSchema } = require('./test.model');
require('mongoose-schema-extend');

const TaskSchema = TestSchema.extend({
  start_date: {
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
    default: 2,
    max: 3,
    min: 1,
  },
});

const Task = mongoose.model('Task', TaskSchema);
module.exports = Task;
