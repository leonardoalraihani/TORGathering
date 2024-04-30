import requests
from bs4 import BeautifulSoup
import os
import threading
import socks
from stem.process import *
import urllib.parse
import sys

def start_tor(socks_port):
    print(f"Starting Tor process with SOCKS port {socks_port}...")
    try:
        tor_process = stem.process.launch_tor_with_config(
            config = {
                'SocksPort': str(socks_port),
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
    def __init__(self, socks_port, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.socks_port = socks_port

def main(url):
    num_threads = 5  # Number of threads
    output_directory = "downloaded_files"
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)
    
    tor_processes = []
    threads = []

    # Start Tor processes and threads
    for i in range(num_threads):
        socks_port = 9050 + i
        tor_process = start_tor(socks_port)
        if tor_process:
            tor_processes.append(tor_process)
            thread = DownloadThread(socks_port=socks_port, target=download_files_from_page, args=(url, output_directory, socks_port))
            thread.start()
            threads.append(thread)

    # Wait for all threads to complete
    for thread in threads:
        thread.join()

    # Stop Tor processes
    for tor_process in tor_processes:
        stop_tor(tor_process)

    print("Download completed!")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python script.py <URL>")
    else:
        url = sys.argv[1]
        main(url)
