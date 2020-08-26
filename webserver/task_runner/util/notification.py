import smtplib
import socket
from email import encoders
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr
from socket import timeout

# sys.path.append('.')
from app.main.config import get_config

notification_chain = []
APP = None


BODY_TEMPLATE = 'Test suite {} is {}.\n\nFor details please see http://localhost:9527/#/test-report/test-detail?task_id={}&organization={}{}'
SUBJECT_TEMPLATE = 'Test Report for {}'


def _format_addr(s):
    name, addr = parseaddr(s)
    return formataddr((Header(name).encode(), addr))

def send_email(task):
    from_addr = get_config().FROM_ADDR
    password = get_config().SMTP_PASSWORD
    smtp_user = get_config().SMTP_USER
    smtp_server = get_config().SMTP_SERVER
    smtp_server_port = get_config().SMTP_SERVER_PORT
    smtp_always_cc = get_config().SMTP_ALWAYS_CC

    body_msg = BODY_TEMPLATE.format(task.test.test_suite, task.status, task.id, task.test.organization.id, '&team=%s' % task.test.team.id if task.test.team else '')
    msg = MIMEText(body_msg, 'plain', 'utf-8')
    msg['From'] = _format_addr(from_addr)
    msg['To'] = _format_addr(task.tester.email)
    msg['cc'] = _format_addr(smtp_always_cc)
    msg['Subject'] = Header(SUBJECT_TEMPLATE.format(task.test.test_suite))

    try:
        with smtplib.SMTP(smtp_server, smtp_server_port, timeout=5) as server:
            # server.starttls()
            # server.set_debuglevel(1)
            try:
                server.login(smtp_user, password)
            except smtplib.SMTPAuthenticationError:
                APP.logger.error('SMTP authentication failed')
                return
            try:
                server.sendmail(from_addr, [task.tester.email], msg.as_string())
            except smtplib.SMTPServerDisconnected:
                APP.logger.error('SMTP sending mail failed')
    except TimeoutError:
        APP.logger.error('SMTP server connecting timeout')
        return
    except timeout:
        APP.logger.error('SMTP server connecting socket timeout')
        return
    except ConnectionRefusedError:
        APP.logger.error('SMTP server connecting refused')
        return
    except socket.gaierror:
        APP.logger.error('Network is not available')
        return

def notification_chain_init(app):
    global APP
    if send_email not in notification_chain:
        notification_chain.append(send_email)
    APP = app

def notification_chain_call(task):
    for caller in notification_chain:
        caller(task)
