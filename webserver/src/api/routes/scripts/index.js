const express = require('express');
const controller = require('../../controllers/script.controller');

const router = express.Router();

router
  .route('/:script')
  .get(controller.get);

module.exports = router;
