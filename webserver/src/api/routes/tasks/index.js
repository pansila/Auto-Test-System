const express = require('express');
const controller = require('../../controllers/task.controller');

const router = express.Router();

router
  .route('/')
  .get(controller.get);

router
  .route('/run/:task')
  .post(controller.run);

router
  .route('/run/:task')
  .get(controller.polling);

module.exports = router;
