import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from bs4 import BeautifulSoup
import os
import threading
import socks
import time
from stem.process import *
import urllib.parse
import sys
import colorama
from colorama import Fore, Style

# Disable SSL certificate verification warning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

def start_tor(data_directory, socks_port):
    print(f"Starting Tor process with SOCKS port {socks_port}...")
    try:
        # Ensure that the parent directory exists
        os.makedirs(data_directory, exist_ok=True)
        
        tor_process = stem.process.launch_tor_with_config(
            config = {
                'SocksPort': str(socks_port),
                'DataDirectory': data_directory,
                'ExitNodes': '{us}'  # Optional: specify exit nodes
            },
            init_msg_handler = print,
        )
        print(f"Tor process with SOCKS port {socks_port} started.")
        return tor_process
    except Exception as e:
        print(f"Timeout occurred while starting Tor process: {str(e)}")
        return None

def stop_tor(tor_process):
    if tor_process:
        print("Stopping Tor process...")
        tor_process.kill()
        print("Tor process stopped.")

def download_file(url, filepath, socks_port, max_retries=99999):
    retries = 0
    while retries < max_retries:
        try:
            print(f"Downloading {url} to {filepath}...")
            session = requests.session()
            session.proxies = {
                'http': f'socks5h://localhost:{socks_port}',
                'https': f'socks5h://localhost:{socks_port}'
            }
            session.verify = False
            response = session.get(url, stream=True)
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        f.write(chunk)
                        print(f"Written chunk to {filepath}.")
            print(f"Download of {url} completed.")
            return  # Exit the function if download is successful
        except Exception as e:
            print(f"Error downloading {url}: {str(e)}")
            retries += 1
            if retries < max_retries:
                print(f"Retrying download... Attempt {retries}/{max_retries}")
                time.sleep(5)  # Wait for a few seconds before retrying
            else:
                print("Max retries exceeded. Failed to download the file.")
                if os.path.exists(filepath):
                    os.remove(filepath)
                return  # Exit the function if max retries exceeded

def get_links_from_page(url, socks_port, max_retries=99999):
    print(Fore.GREEN + Style.BRIGHT + "Getting" + Style.RESET_ALL + " links from", url, '...')
    links = {'directories': [], 'files': []}
    retries = 0
    while retries < max_retries:
        try:
            session = requests.session()
            session.proxies = {
                'http': f'socks5h://localhost:{socks_port}',
                'https': f'socks5h://localhost:{socks_port}'
            }
            session.verify = False
            
            response = session.get(url)
            soup = BeautifulSoup(response.content, 'html.parser')
            for link in soup.find_all('a', href=True):
                href = link['href']
                if href.endswith('/'):
                    links['directories'].append(href)
                    print(f"Found directory link: {href}")
                elif '.' in href:
                    links['files'].append(href)
                    print(f"Found file link: {href}")
            print(f"Links extraction from {url} completed.")
            return links  # Exit the function if links extraction is successful
        except Exception as e:
            print(f"Error getting links from {url}: {str(e)}")
            retries += 1
            if retries < max_retries:
                print(f"Retrying links extraction... Attempt {retries}/{max_retries}")
                time.sleep(5)  # Wait for a few seconds before retrying
            else:
                print("Max retries exceeded. Failed to extract links.")
                return links  # Return the links extracted so far


def download_files_from_page(url, directory, socks_port):
    links = get_links_from_page(url, socks_port)
    for file in links['files']:
        file_url = urllib.parse.urljoin(url, file)
        filename = os.path.join(directory, os.path.basename(file))
        if os.path.exists(filename):
            local_size = os.path.getsize(filename)
            remote_size = get_remote_file_size(file_url, socks_port)
            if local_size != remote_size:
                print(f"File {filename} already exists but sizes do not match. Re-downloading...")
                os.remove(filename)
                download_file(file_url, filename, socks_port)
            else:
                print(f"File {filename} already exists. Skipping download.")
        else:
            download_file(file_url, filename, socks_port)
    for directory_link in links['directories']:
        directory_url = urllib.parse.urljoin(url, directory_link)
        subdir = os.path.join(directory, os.path.basename(directory_link))
        if not os.path.exists(subdir):
            os.makedirs(subdir)
        download_files_from_page(directory_url, subdir, socks_port)

def get_remote_file_size(url, socks_port):
    try:
        session = requests.session()
        session.proxies = {
            'http': f'socks5h://localhost:{socks_port}',
            'https': f'socks5h://localhost:{socks_port}'
        }
        session.verify = False
        response = session.get(url, stream=True)
        # Check if 'content-length' header exists
        if 'content-length' in response.headers:
            return int(response.headers.get('content-length'))
        else:
            print(f"No 'content-length' header for {url}.")
            return 0  # Or handle this situation differently
    except Exception as e:
        print(f"Error getting file size for {url}: {str(e)}")
        return 0


class DownloadThread(threading.Thread):
    def __init__(self, data_directory, socks_port, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data_directory = data_directory
        self.socks_port = socks_port

    def run(self):
        print(f"Thread {self.name} started.")
        tor_process = start_tor(self.data_directory, self.socks_port)
        if tor_process:
            try:
                download_files_from_page(url, self.data_directory, self.socks_port)
            finally:
                stop_tor(tor_process)
        print(f"Thread {self.name} finished.")

def main(url):
    print(f"Downloading files from {url}...")
    num_threads = 3  # Number of threads
    output_directory = "data_directory"
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)
    
    threads = []

    # Start threads
    for i in range(num_threads):
        data_directory = os.path.join("data_directory", f"tor_{i}")
        socks_port = 9050 + i
        thread = DownloadThread(data_directory, socks_port)
        thread.start()
        threads.append(thread)

    # Wait for all threads to complete
    for thread in threads:
        thread.join()

    print("Download completed!")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python script.py <URL>")
    else:
        url = sys.argv[1]
        main(url)
