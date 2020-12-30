from app.main.model.database import BlacklistToken

from sanic.log import logger
from ..util.response import *

async def save_token(token):
    blacklist_token = BlacklistToken(token=token)
    try:
        # insert the token
        await blacklist_token.commit()
        return response_message(SUCCESS)
    except Exception as e:
        logger.exception(e)
        return response_message(UNKNOWN_ERROR)
