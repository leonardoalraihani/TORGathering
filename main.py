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
import queue

# Disable SSL certificate verification warning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

class RoundRobinQueue:
    def __init__(self, num_threads):
        self.queue = queue.Queue()
        self.num_threads = num_threads

    def put(self, item):
        self.queue.put(item)

    def get(self):
        try:
            item = self.queue.get(block=False)
            return item
        except queue.Empty:
            return None

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

def download_file(url, filepath, socks_port, max_retries=3):
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
            print(f"Download of {url} " + Fore.GREEN + Style.BRIGHT + "completed.")
            return  # Exit the function if download is successful
        except Exception as e:
            print(Fore.RED + Style.BRIGHT + "Error" + Style.RESET_ALL + f" downloading {url}: {str(e)}")
            retries += 1
            if retries < max_retries:
                print(f"Retrying download... Attempt {retries}/{max_retries}")
                time.sleep(5)  # Wait for a few seconds before retrying
            else:
                print("Max retries exceeded. Failed to download the file.")
                if os.path.exists(filepath):
                    os.remove(filepath)
                return  # Exit the function if max retries exceeded

def get_links_from_page(url, base_url, socks_port, max_retries=3):
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
                full_link = urllib.parse.urljoin(base_url, href)
                if full_link.startswith(base_url):  # Check if the full link is within the base URL
                    if href.endswith('/'):
                        links['directories'].append(href)
                        print(Fore.BLUE + Style.BRIGHT + "Found" + Style.RESET_ALL + f" directory link: {href}")
                    elif '.' in href:
                        links['files'].append(href)
                        print(Fore.BLUE + Style.BRIGHT + "Found" + Style.RESET_ALL + f" file link: {href}")
            print(f"Links extraction from {url}" + Fore.GREEN + Style.BRIGHT + "completed.")
            return links  # Exit the function if links extraction is successful
        except Exception as e:
            print(Fore.RED + Style.BRIGHT + "Error" + Style.RESET_ALL + f" getting links from {url}: {str(e)}")
            retries += 1
            if retries < max_retries:
                print(Fore.YELLOW + Style.BRIGHT + "Retrying" + Style.RESET_ALL + f" links extraction... Attempt {retries}/{max_retries}")
                time.sleep(5)  # Wait for a few seconds before retrying
            else:
                print("Max retries exceeded. Failed to extract links.")
                return links  # Return the links extracted so far

def download_files_from_page(url, directory, socks_port):
    links = get_links_from_page(url, url, socks_port)  # Pass url to get_links_from_page function
    for file in links['files']:
        file_url = urllib.parse.urljoin(url, file)
        filename = os.path.join(directory, os.path.basename(file))
        if os.path.exists(filename):
            local_size = os.path.getsize(filename)
            remote_size = get_remote_file_size(file_url, socks_port)
            if local_size != remote_size:
                print(f"File {filename} already exists but sizes do not match. Resuming download...")
                resume_download(file_url, filename, socks_port, local_size)
            else:
                print(f"File {filename} already exists. Skipping download.")
        else:
            download_file(file_url, filename, socks_port)

    for directory_link in links['directories']:
        directory_url = urllib.parse.urljoin(url, directory_link)
        subdir = os.path.join(directory, os.path.basename(directory_link))
        if not os.path.exists(subdir):
            os.makedirs(subdir)
        download_files_from_page(directory_url, subdir, socks_port)  # Pass socks_port recursively

def resume_download(url, filepath, socks_port, start_byte):
    try:
        print(f"Resuming download of {url} to {filepath} from byte {start_byte}...")
        session = requests.session()
        session.proxies = {
            'http': f'socks5h://localhost:{socks_port}',
            'https': f'socks5h://localhost:{socks_port}'
        }
        session.verify = False
        headers = {'Range': f'bytes={start_byte}-'}
        response = session.get(url, headers=headers, stream=True)
        with open(filepath, 'ab') as f:  # 'ab' mode for appending binary data
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
                    print(f"Written chunk to {filepath}.")
        print(f"Resumed download of {url} " + Fore.GREEN + Style.BRIGHT + "completed.")
    except Exception as e:
        print(Fore.RED + Style.BRIGHT + "Error" + Style.RESET_ALL + f" resuming download of {url}: {str(e)}")


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
        print(Fore.RED + Style.BRIGHT + "Error" + Style.RESET_ALL + f" getting file size for {url}: {str(e)}")
        return 0


class DownloadThread(threading.Thread):
    tor_processes = {}

    def __init__(self, data_directory, socks_port, folder_queue, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data_directory = data_directory
        self.socks_port = socks_port
        self.folder_queue = folder_queue

    def start_tor_process(self):
        if self.socks_port not in self.tor_processes:
            print(f"Starting Tor process with SOCKS port {self.socks_port}...")
            tor_process = start_tor(self.data_directory, self.socks_port)
            if tor_process:
                self.tor_processes[self.socks_port] = tor_process

    def stop_tor_process(self):
        if self.socks_port in self.tor_processes:
            print(f"Stopping Tor process with SOCKS port {self.socks_port}...")
            stop_tor(self.tor_processes[self.socks_port])
            del self.tor_processes[self.socks_port]

    def run(self):
        self.start_tor_process()
        try:
            while True:
                folder_url = self.folder_queue.get()
                if folder_url is None:
                    print(f"Thread {self.name} exiting as no more folders to process")
                    break
                print(f"Thread {self.name} processing {folder_url}")
                download_files_from_page(folder_url, self.data_directory, self.socks_port)
                print(f"Thread {self.name} finished processing {folder_url}")
        finally:
            self.stop_tor_process()


def main(url, num_threads):
    print(f"Downloading files from {url} using {num_threads} threads...")
    output_directory = "data_directory"
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)
    
    threads = []
    folder_queue = RoundRobinQueue(num_threads)

    # Start threads
    for i in range(num_threads):
        data_directory = os.path.join("data_directory", f"tor_{i}")
        socks_port = 9050 + i
        thread = DownloadThread(data_directory, socks_port, folder_queue)
        threads.append(thread)

    # Enqueue the URLs to the folder queue
    folder_queue.put(url)  # Enqueue the initial URL
    for thread in threads:
        thread.start()  # Start each thread

    # Wait for all threads to complete
    for thread in threads:
        thread.join()

    print("Download completed.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python script.py <URL> <num_threads>")
    else:
        url = sys.argv[1]
        num_threads = int(sys.argv[2])
        main(url, num_threads)