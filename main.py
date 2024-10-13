import email
import imaplib
import os
import re
import time
import urllib.parse
from email.header import decode_header
from typing import Optional

import requests
from bs4 import BeautifulSoup, Tag
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

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
    else:
        print("No download link found.")
    return None


def download_files_from_js_page(url: str):
    # Set up headless browser options
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in headless mode
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    # Start the browser using webdriver-manager for automatic driver installation
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=chrome_options
    )

    try:
        print(f"Visiting {url}...")
        driver.get(url)

        # Wait for the download links to be clickable (use explicit wait)
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "DOWNLOAD"))
        )

        # Find the download anchor link
        download_links = driver.find_elements(By.PARTIAL_LINK_TEXT, "DOWNLOAD")
        print(f"Found {len(download_links)} download links.")

        # Use XPath to locate the nearest preceding <p> tag that contains the file name
        # In XPath, "preceding" is used to find an element that appears before the anchor
        for link in download_links:
            try:
                file_name_element = link.find_element(By.XPATH, "./preceding::p[1]")
                file_name = file_name_element.text  # Extract the actual file name

                print(f"Found file name: {file_name}")

                # Get the download URL from the anchor tag
                download_url = link.get_attribute("href")

                if download_url:
                    print(f"Downloading from: {download_url}")
                    # Use the extracted file name when saving the file
                    download_file(download_url, file_name)
            except Exception as e:
                print(f"An error occurred while processing download links: {e}")

    except Exception as e:
        print(f"An error occurred while downloading files: {e}")
    finally:
        driver.quit()


# TODO: throw  in cloud solution
def download_file(url, file_name):
    try:
        response = requests.get(url, stream=True)

        # Check if the response was successful
        if response.status_code == 200:
            # Check the Content-Type to ensure it's a ZIP file
            if "application/zip" in response.headers.get("Content-Type", ""):
                with open(file_name, "wb") as file:
                    for chunk in response.iter_content(
                        chunk_size=8192
                    ):  # Download in chunks
                        file.write(chunk)
                print(f"File saved as: {file_name}")
            else:
                print(
                    f"Unexpected content type: {response.headers.get('Content-Type')}"
                )
                print("The file may not be a ZIP file.")
        else:
            print(
                f"Failed to download file from {url}. Status code: {response.status_code}"
            )
            print(
                "Response content:", response.text
            )  # Log response content for debugging

    except Exception as e:
        print(f"An error occurred during file download: {e}")


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
                                    link = parse_email_content(html_content)
                                    if link:
                                        download_files_from_js_page(link)
                                    else:
                                        print("No download link found in the email.")
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
    monitor_email()
