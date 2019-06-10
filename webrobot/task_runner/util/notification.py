import smtplib
import socket
from email import encoders
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr
from socket import timeout

# sys.path.append('.')
from app.main.config import get_config

BODY_TEMPLATE = 'Test suite {} is {}.\n\nFor details please see http://localhost:5000/testresult/{}/log.html'
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

    msg = MIMEText(BODY_TEMPLATE.format(task.test.test_suite, task.status, task.id), 'plain', 'utf-8')
    msg['From'] = _format_addr(from_addr)
    msg['To'] = _format_addr(task.tester.email)
    msg['cc'] = _format_addr(smtp_always_cc)
    msg['Subject'] = Header(SUBJECT_TEMPLATE.format(task.test.test_suite))

    try:
        server = smtplib.SMTP(smtp_server, smtp_server_port, timeout=5)
    except TimeoutError:
        print('SMTP server connecting timeout')
        return
    except timeout:
        print('SMTP server connecting socket timeout')
        return
    except ConnectionRefusedError:
        print('SMTP server connecting refused')
        return

    # server.starttls()
    # server.set_debuglevel(1)
    try:
        server.login(smtp_user, password)
    except smtplib.SMTPAuthenticationError:
        print('SMTP authentication failed')
        server.quit()
        return
    server.sendmail(from_addr, [task.tester.email], msg.as_string())
    server.quit()
