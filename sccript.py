import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, unquote
import concurrent.futures
from tqdm import tqdm
import os
from urllib.parse import urlparse

def get_base_url(course_url):
    parsed_url = urlparse(course_url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    return base_url

def fetch_logintoken(session, login_url):
    response = session.get(login_url)
    soup = BeautifulSoup(response.text, 'html.parser')
    token_input = soup.find('input', {'name': 'logintoken'})
    return token_input['value'] if token_input else None

def login_moodle(base_url, username, password):
    login_url = urljoin(base_url, 'login/index.php')
    session = requests.Session()
    logintoken = fetch_logintoken(session, login_url)

    if not logintoken:
        raise ValueError("Unable to find login token")

    payload = {
        'logintoken': logintoken,
        'username': username,
        'password': password
    }

    response = session.post(login_url, data=payload)
    print("login status: ", response.status_code)
    return session


def download_file(session, url, intermediate_url):
    local_filename = url.split('/')[-1]
    local_filename = unquote(local_filename)
    with session.get(url, stream=True) as r:
        with open(local_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    return local_filename, intermediate_url

def resolve_redirect(session, url):
    response = session.get(url, allow_redirects=True)
    return response.url  # Returns the final destination URL after following the redirect

def find_download_link(session, intermediate_url):
    response = session.get(intermediate_url)
    soup = BeautifulSoup(response.text, 'html.parser')
    download_link = soup.find(lambda tag: tag.name == 'a' and 'pluginfile.php' in tag.get('href', ''))
    return download_link['href'] if download_link else None

def download_all_files(session, course_url, max_workers):
    response = session.get(course_url)
    soup = BeautifulSoup(response.text, 'html.parser')
    download_links = []
    intermediate_links = []

    for link in soup.find_all('a'):
        href = link.get('href')
        if href and 'mod/resource/view.php' in href:
            intermediate_links.append(href)
            actual_download_link = find_download_link(session, href)
            if actual_download_link:
                download_links.append((actual_download_link, href))
        elif href and 'pluginfile.php' in href:
            download_links.append((href, href))

    downloaded_files = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(tqdm(executor.map(lambda url_pair: download_file(session, url_pair[0], url_pair[1]), download_links), total=len(download_links)))
        downloaded_files.extend(results)

    # Only store the filename, not the full path
    downloaded_files = [(os.path.basename(filename), intermediate_url) for filename, intermediate_url in results]

    return downloaded_files

def modify_html_with_downloads(html_file, downloaded_files):
    with open(html_file, 'r', encoding='utf-8') as file:
        soup = BeautifulSoup(file, 'html.parser')

    # Remove all script tags
    for script in soup.find_all('script'):
        script.decompose()

    # Update anchor tags
    for filename, intermediate_url in downloaded_files:
        for link in soup.find_all('a', href=intermediate_url):
            link['href'] = filename  # Update with the correct relative path
            link['target'] = '_blank'  # Open in a new tab
            link['rel'] = 'noopener noreferrer'  # Security measures
            if link.has_attr('onclick'):
                del link['onclick']  # Remove onclick attribute

    with open(html_file, 'w', encoding='utf-8') as file:
        file.write(str(soup))


def save_html_to_disk(html_content, filename):
    with open(filename, 'w', encoding='utf-8') as file:
        file.write(html_content)

# Configuration
course_url = 'https://elearning.ohmportal.de/course/view.php?id=1234'
base_url = get_base_url(course_url)
username = 'lkajasdf'
password = 'afagaedgasfsad'
max_workers = 10 # Maximum number of concurrent downloads

# Usage
session = login_moodle(base_url, username, password)
course_page_response = session.get(course_url)
save_html_to_disk(course_page_response.text, 'course_page.html')
downloaded_files = download_all_files(session, course_url, max_workers)
modify_html_with_downloads('course_page.html', downloaded_files)
