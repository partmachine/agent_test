import win32com.client
import smtplib
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging

class EmailHandler:
    def __init__(self, smtp_server, email_address, password, smtp_port=587):
        self.smtp_server = smtp_server
        self.email_address = email_address
        self.password = password
        self.smtp_port = smtp_port
        self.smtp_connection = None
        logging.basicConfig(level=logging.INFO)

    def connect_imap(self):
        try:
            self.outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
            logging.info("Successfully connected to Outlook MAPI")
        except Exception as e:
            logging.error(f"Failed to connect to Outlook MAPI: {e}")

    def connect_smtp(self):
        try:
            self.smtp_connection = smtplib.SMTP(self.smtp_server, self.smtp_port)
            self.smtp_connection.starttls()
            self.smtp_connection.login(self.email_address, self.password)
            logging.info("Successfully connected to SMTP server")
        except Exception as e:
            logging.error(f"Failed to connect to SMTP server: {e}")

    def disconnect_smtp(self):
        if self.smtp_connection:
            self.smtp_connection.quit()
            logging.info("Disconnected from SMTP server")

    def fetch_unread_emails(self):
        try:
            self.connect_imap()
            inbox = self.outlook.GetDefaultFolder(6)
            messages = inbox.Items
            unread_messages = messages.Restrict("[Unread]=True")
            emails = []

            for msg in unread_messages:
                emails.append({
                    'subject': msg.Subject,
                    'from': msg.SenderName,
                    'to': msg.To,
                    'date': msg.ReceivedTime,
                    'body': msg.Body
                })

            return emails

        except Exception as e:
            logging.error(f"Failed to fetch unread emails: {e}")
            return []

    def send_email(self, to_address, subject, body):
        try:
            self.connect_smtp()
            msg = MIMEMultipart()
            msg['From'] = self.email_address
            msg['To'] = to_address
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            self.smtp_connection.sendmail(self.email_address, to_address, msg.as_string())
            logging.info("Email sent successfully")
        except Exception as e:
            logging.error(f"Failed to send email: {e}")
        finally:
            self.disconnect_smtp()

# Example usage
if __name__ == "__main__":
    smtp_server = "smtp-mail.outlook.com"
    email_address = "rene.vangeffen@live.nl"
    password = "141368068Andriesplein@6"

    email_handler = EmailHandler(smtp_server, email_address, password)
    unread_emails = email_handler.fetch_unread_emails()
    for email in unread_emails:
        print(f"Subject: {email['subject']}, From: {email['from']}")

    email_handler.send_email("recipient@example.com", "Test Subject", "This is a test email.")
