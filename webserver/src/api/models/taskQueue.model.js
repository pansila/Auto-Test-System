const mongoose = require('mongoose');
const { TaskSchema } = require('./task.model');

// per endpoint per priority flat queue
const EndpointTaskQueueSchema = new mongoose.Schema({
  schema_version: {
    type: String,
    default: '1',
  },
  endpoint: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'TaskQueue',
  },
  priority: {
    type: Number,
    default: 2,
    max: 3,
    min: 1,
  },
  tasks: [TaskSchema],
});

// per endpoint entry queue
const TaskQueueSchema = new mongoose.Schema({
  schema_version: {
    type: String,
    default: '1',
  },
  endpoint_address: {
    type: String,
  },
  // array index (0, 1, 2) maps to priority (1, 2, 3).
  priorities: [{
    type: mongoose.Schema.Types.ObjectId,
    ref: 'EndpointTaskQueue',
  }],
});

TaskQueueSchema.statics = {
  async push(doc, priority = 2, endpointAddress) {
    try {
      const queue = await this.findOne({ priority, endpoint_address: endpointAddress }).exec();
      const result = await queue.findOneAndUpdate(
        { priority },
        { $push: { tasks: doc } },
      ).exec();
      console.log(result);
    } catch (error) {
      console.error(error);
    }
  },
  // async pop(priority = 2, endpointAddress) {
  //   try {
  //     const queue = await this.findOne({ priority, endpoint_address: endpointAddress }).exec();
  //     try {
  //       const task = await queue.findOne(
  //         {
  //           priority,
  //           tasks: {},
  //         },
  //         { 'tasks.$': 1 },
  //       ).exec();
  //       try {
  //         const result = await task.findOneAndUpdate(
  //           { status: 'Pending' },
  //           { $set: { status: 'Running' } },
  //         ).exec();
  //         try {
  //           const t = await task.findOneAndUpdate(
  //             { status: 'Pending' },
  //             { $set: { status: 'Running' } },
  //           ).exec();
  //           console.log(result);
  //           return result;
  //         } catch (error) {
  //           console.error(error);
  //           return undefined;
  //         }
  //       } catch (error) {
  //         console.error(error);
  //         return undefined;
  //       }
  //     } catch (error) {
  //       console.error(error);
  //       return undefined;
  //     }
  //   } catch (error) {
  //     console.error(error);
  //     return undefined;
  //   }
  // },
  // async get() {
  //   try {
  //     const result = await this.findOneAndUpdate(
  //       { priority: 1 },
  //       { $pop: { tasks: -1 } },
  //     ).exec();
  //     console.log(result);
  //     return result;
  //   } catch (error) {
  //     console.error(error);
  //     return undefined;
  //   }
  // },
};

exports.TaskQueue = mongoose.model('TaskQueue', TaskQueueSchema);
exports.EndpointTaskQueue = mongoose.model('EndpointTaskQueue', EndpointTaskQueueSchema);
