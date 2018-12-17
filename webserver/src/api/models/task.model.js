const mongoose = require('mongoose');

const taskSchema = new mongoose.Schema({
  schema_version: {
    type: String,
    default: '1',
  },
  test_suite: {
    type: 'String',
    required: true,
    index: true,
    unique: true,
    trim: true,
  },
  test_cases: [String],
  parameters: {
    type: Map,
    of: String,
  },
  path: {
    type: String,
    maxlength: 300,
  },
  author: {
    type: String,
    maxlength: 50,
  },
  create_date: { type: Date },
  update_date: { type: Date },
}, { collection: 'test' });

taskSchema.statics = {
  async get_list() {
    try {
      const result = await this.find({}).exec();
      console.log(result);
      return result.map(test => test.test_suite);
    } catch (error) {
      console.log(error);
      return [];
    }
  },
};

const Task = mongoose.model('test', taskSchema);
module.exports = Task;
