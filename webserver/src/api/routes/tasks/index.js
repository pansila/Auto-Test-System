const express = require('express');
const controller = require('../../controllers/task.controller');

const router = express.Router();

router
  .route('/')
  .get(controller.get);

// router
//   .route('/task?run=param')
//   .post(controller.run);

module.exports = router;
