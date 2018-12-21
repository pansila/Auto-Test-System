const express = require('express');
const taskQueueController = require('../../controllers/taskQueue.controller');

const router = express.Router();

router
  .route('/')
  .get(taskQueueController.get)
  .post(taskQueueController.post);

module.exports = router;
