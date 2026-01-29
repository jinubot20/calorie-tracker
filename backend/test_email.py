import smtplib
import os
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

def send_test_email():
    gmail_user = os.getenv("GMAIL_USER")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")
    personal_email = os.getenv("PERSONAL_EMAIL")

    msg = EmailMessage()
    msg.set_content("Hello Jit Hon! This is a test email from your Jinu bot. Everything is working perfectly!")
    msg['Subject'] = 'Jinu Bot Connection Test'
    msg['From'] = gmail_user
    msg['To'] = personal_email

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(gmail_user, gmail_password)
            smtp.send_message(msg)
        return "Success"
    except Exception as e:
        return str(e)

if __name__ == "__main__":
    result = send_test_email()
    print(result)
