const mongoose = require('mongoose');

const TestSchema = new mongoose.Schema({
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
});

TestSchema.statics = {
  async get_list() {
    try {
      const result = await this.find({}).exec();
      return result.map(test => test.test_suite);
    } catch (error) {
      return [];
    }
  },
};

const Test = mongoose.model('Test', TestSchema);

module.exports = Test;
