import email
import imaplib
import os
import re
import time
import urllib.parse
from email.header import decode_header
from typing import Optional

from bs4 import BeautifulSoup, NavigableString, Tag
from dotenv import load_dotenv

load_dotenv()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "")
APP_PASSWORD = os.getenv("APP_PASSWORD", "")
IMAP_SERVER = "imap.gmail.com"
MAILBOX = "INBOX"
CHECK_INTERVAL = 10

DOWNLOAD_LINK_PATTERN = os.getenv("DOWNLOAD_LINK_PATTERN", "")


def parse_email_content(content: str) -> Optional[str]:
    soup = BeautifulSoup(content, "html.parser")

    download_link = soup.find("a", href=DOWNLOAD_LINK_PATTERN)

    if not download_link:
        # If not found, try looking for any link with text containing 'download'
        download_link = soup.find("a", string=re.compile(r"download", re.I))

    if download_link and isinstance(download_link, Tag):
        href = download_link.get("href")
        if href:
            if isinstance(href, list):
                # If href is a list, join its elements
                href = " ".join(href)
            if isinstance(href, str):
                cleaned_url = href.replace("=\n", "").replace("=3D", "=")
                decoded_url = urllib.parse.unquote(cleaned_url)
                print(f"Download link found: {decoded_url}")
                return decoded_url
            print(f"Unexpected href type: {type(href)}")
        else:
            print("href attribute is None")
    elif download_link and isinstance(download_link, NavigableString):
        print(f"Found NavigableString instead of Tag: {download_link}")
        return None

    print("No download link found.")
    return None


def monitor_email():
    last_checked_email_id = None
    while True:
        imap = None
        try:
            print("Connecting to the IMAP server...")
            imap = imaplib.IMAP4_SSL(IMAP_SERVER)
            imap.login(EMAIL_ADDRESS, APP_PASSWORD)
            imap.select(MAILBOX)

            _, message_numbers = imap.search(None, "ALL")
            if not message_numbers[0]:
                print("No messages found in the mailbox.")
                continue

            latest_email_id = message_numbers[0].split()[-1]
            if last_checked_email_id is None:
                last_checked_email_id = latest_email_id
                print("Initialized. Waiting for new emails...")
                continue

            if latest_email_id != last_checked_email_id:
                print("New email(s) found!")
                new_emails = message_numbers[0].split()[int(last_checked_email_id) :]
                for num in reversed(new_emails):
                    _, msg_data = imap.fetch(num, "(RFC822)")
                    for response in msg_data:
                        if isinstance(response, tuple):
                            email_body = email.message_from_bytes(response[1])
                            subject, _ = decode_header(email_body["Subject"])[0]
                            if isinstance(subject, bytes):
                                subject = subject.decode()
                            print(f"\nSubject: {subject}")

                            for part in email_body.walk():
                                if part.get_content_type() == "text/html":
                                    html_content = part.get_payload(
                                        decode=True
                                    ).decode()
                                    parse_email_content(html_content)
                                    break

                last_checked_email_id = latest_email_id
            else:
                print("No new emails.")

        except imaplib.IMAP4.error as e:
            print(f"An IMAP error occurred: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
        finally:
            if imap:
                try:
                    imap.close()
                    imap.logout()
                except:
                    pass

        print(f"Waiting for {CHECK_INTERVAL} seconds before checking again...")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    print("Email Monitor and Parser for Download Links")
    monitor_email()
