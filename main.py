import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from bs4 import BeautifulSoup
import os
import threading
import socks
from stem.process import *
import urllib.parse
import sys

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
        print(f"Timeout occurred while starting Tor process.{str(e)}")
        return None

def stop_tor(tor_process):
    if tor_process:
        print("Stopping Tor process...")
        tor_process.kill()
        print("Tor process stopped.")

def download_file(url, filepath, socks_port):
    try:
        session = requests.session()
        session.proxies = {
            'http': f'socks5h://localhost:{socks_port}',
            'https': f'socks5h://localhost:{socks_port}'
        }
        response = session.get(url, stream=True)
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
    except Exception as e:
        print(f"Error downloading {url}: {str(e)}")
        if os.path.exists(filepath):
            os.remove(filepath)

def get_links_from_page(url, socks_port):
    links = {'directories': [], 'files': []}
    try:
        session = requests.session()
        session.proxies = {
            'http': f'socks5h://localhost:{socks_port}',
            'https': f'socks5h://localhost:{socks_port}'
        }
        response = session.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        for link in soup.find_all('a', href=True):
            href = link['href']
            if href.endswith('/'):
                links['directories'].append(href)
            elif '.' in href:
                links['files'].append(href)
    except Exception as e:
        print(f"Error getting links from {url}: {str(e)}")
    return links

def download_files_from_page(url, directory, socks_port):
    links = get_links_from_page(url, socks_port)
    for file in links['files']:
        file_url = urllib.parse.urljoin(url, file)
        filename = os.path.join(directory, os.path.basename(file))
        if os.path.exists(filename):
            local_size = os.path.getsize(filename)
            remote_size = get_remote_file_size(file_url, socks_port)
            if local_size != remote_size:
                os.remove(filename)
                download_file(file_url, filename, socks_port)
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
        response = session.head(url)
        return int(response.headers['content-length'])
    except Exception as e:
        print(f"Error getting file size for {url}: {str(e)}")
        return 0

class DownloadThread(threading.Thread):
    def __init__(self, data_directory, socks_port, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data_directory = data_directory
        self.socks_port = socks_port

    def run(self):
        tor_process = start_tor(self.data_directory, self.socks_port)
        if tor_process:
            try:
                download_files_from_page(url, self.data_directory, self.socks_port)
            finally:
                stop_tor(tor_process)

def main(url):
    num_threads = 5  # Number of threads
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
