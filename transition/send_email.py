# python
SMTP_SERVER = "postfix-mail"
SMTP_PORT = 587
FROM_ADDRESS = "clock@wisc.edu"

import smtplib
import logging
from os.path import basename
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
from typing import Union

logging = logging.getLogger('chtc_projects_on_ospool')

def send_email(send_from: str, send_to: Union[str, list], subject: str, text: str, files=None, server=SMTP_SERVER, port=SMTP_PORT):

    msg = MIMEMultipart()
    msg['From'] = send_from
    msg['To'] = send_to if isinstance(send_to, str) else ', '.join(send_to)
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = subject

    msg.attach(MIMEText(text))

    for f in files or []:
        with open(f, "rb") as fil:
            part = MIMEApplication(
                fil.read(),
                Name=basename(f)
            )
        part['Content-Disposition'] = 'attachment; filename="%s"' % basename(f)
        msg.attach(part)

    smtp = smtplib.SMTP(server, port=port)
    smtp.sendmail(send_from, send_to, msg.as_string())
    smtp.close()


if __name__ == "__main__":
    import argparse
    import sys
    from pathlib import Path

    def _split_list(items):
        out = []
        for it in items or []:
            for part in str(it).split(','):
                p = part.strip()
                if p:
                    out.append(p)
        return out

    parser = argparse.ArgumentParser(description="Send an email via send_email()")
    parser.add_argument("--from", dest="send_from", default=FROM_ADDRESS,
                        help="From address (default: %(default)s)")
    parser.add_argument("--to", dest="to", required=True, nargs="+",
                        help="Recipient(s). Pass multiple times or comma-separated list.")
    parser.add_argument("--subject", dest="subject", default="", help="Email subject")
    text_group = parser.add_mutually_exclusive_group()
    text_group.add_argument("--text", dest="text", help="Email body text")
    text_group.add_argument("--text-file", dest="text_file", help="Path to file containing body text")
    parser.add_argument("--file", dest="files", action="append", default=[],
                        help="Attachment file path. Can be used multiple times or comma-separated.")
    parser.add_argument("--server", dest="server", default=SMTP_SERVER,
                        help="SMTP server (default: %(default)s)")

    args = parser.parse_args()

    # Normalize recipients and attachments
    recipients = _split_list(args.to)
    attachments = _split_list(args.files)

    # Read text from file if requested
    body_text = ""
    if args.text is not None:
        body_text = args.text
    elif args.text_file is not None:
        p = Path(args.text_file)
        if not p.exists():
            print(f"Text file not found: {args.text_file}", file=sys.stderr)
            sys.exit(2)
        body_text = p.read_text()

    try:
        send_email(args.send_from, recipients, args.subject, body_text, attachments, args.server)
    except Exception as e:
        print(f"send_email failed: {e}", file=sys.stderr)
        sys.exit(1)
    else:
        sys.exit(0)
