import asyncio
import smtplib
import socket
from async_files.utils import async_wraps
from email import encoders
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr
from socket import timeout

# sys.path.append('.')
from app.main.config import get_config
from sanic.log import logger

notification_chain = []
APP = None


BODY_TEMPLATE = 'Test suite {} is {}.\n\nFor details please see http://localhost:9527/#/test-report/test-detail?task_id={}&organization={}{}'
SUBJECT_TEMPLATE = 'Test Report for {}'


def _format_addr(s):
    name, addr = parseaddr(s)
    return formataddr((Header(name).encode(), addr))

async def send_email(task):
    from_addr = get_config().FROM_ADDR
    password = get_config().SMTP_PASSWORD
    smtp_user = get_config().SMTP_USER
    smtp_server = get_config().SMTP_SERVER
    smtp_server_port = get_config().SMTP_SERVER_PORT
    smtp_always_cc = get_config().SMTP_ALWAYS_CC

    test = await task.test.fetch()
    organization = await test.organization.fetch()
    team = None
    if test.team:
        team = await test.team.fetch()
    tester = await task.tester.fetch()

    body_msg = BODY_TEMPLATE.format(test.test_suite, task.status, task.pk, organization.pk, '&team=%s' % team.pk if team else '')
    msg = MIMEText(body_msg, 'plain', 'utf-8')
    msg['From'] = _format_addr(from_addr)
    msg['To'] = _format_addr(tester.email)
    msg['cc'] = _format_addr(smtp_always_cc)
    msg['Subject'] = Header(SUBJECT_TEMPLATE.format(test.test_suite))

    try:
        server = await async_wraps(smtplib.SMTP)(smtp_server, smtp_server_port, timeout=5)
    except TimeoutError:
        logger.error('SMTP server connecting timeout')
        return
    except timeout:
        logger.error('SMTP server connecting socket timeout')
        return
    except ConnectionRefusedError:
        logger.error('SMTP server connecting refused')
        return
    except socket.gaierror:
        logger.error('Network of SMTP is not available')
        return
    except:
        exc_type, exc_value, exc_tb = sys.exc_info()
        APP.logger.error(f'Un-catched error happened: {exc_type}, {exc_value}')
    else:
        # await async_wraps(server.starttls)()
        # await async_wraps(server.set_debuglevel)(1)
        try:
            await async_wraps(server.login)(smtp_user, password)
        except smtplib.SMTPAuthenticationError:
            logger.error('SMTP authentication failed')
            await async_wraps(server.quit)()
            return
        await async_wraps(server.sendmail)(from_addr, [task.tester.email], msg.as_string())
        await async_wraps(server.quit)()

def notification_chain_init(app):
    notification_chain.append(send_email)

async def notification_chain_call(task):
    # notifications = [callee(task) for callee in notification_chain]
    # await asyncio.gather(*notifications)
    for notifier in notification_chain:
        asyncio.create_task(notifier(task))
