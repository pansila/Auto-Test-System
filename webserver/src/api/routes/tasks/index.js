const express = require('express');
const taskController = require('../../controllers/task.controller');

const router = express.Router();

router
  .route('/')
  .get(taskController.get);

router
  .route('/run/:task')
  .post(taskController.run);

router
  .route('/run/:task')
  .get(taskController.polling);

module.exports = router;
