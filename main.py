import os
import time
import pickle
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from threading import Lock
from urllib.parse import urljoin
from requests.auth import HTTPBasicAuth
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()

HEADERS = {"User-Agent": "Mozilla/5.0"}
BASE_URL = "https://hopamchuan.com"
GENRE_URL = f"{BASE_URL}/genre"
CACHE_DIR = "cache"
TIMEOUT = 10

WP_SITE_URL = os.getenv("WP_SITE_URL")
WP_URL_PUBLISH_POST = f"{WP_SITE_URL}/wp-json/wp/v2/posts"
WP_URL_CATEGORY = f"{WP_SITE_URL}/wp-json/wp/v2/categories"
WP_USERNAME = os.getenv("WP_USERNAME")
WP_PASSWORD = os.getenv("WP_PASSWORD")
DELAY_POSTING = os.getenv("DELAY_POSTING")

os.makedirs(CACHE_DIR, exist_ok=True)
crawled_urls_file = os.path.join(CACHE_DIR, "crawled.pkl")
post_lock = Lock()

def fetch_html(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
        return response.content
    except Exception as e:
        print(f"[ERROR] fetch_html {url}: {e}")

        return None

def get_genres():
    content = fetch_html(GENRE_URL)

    if not content:
        return []

    soup = BeautifulSoup(content, "html.parser")
    genres = []

    for tag in soup.select('a:has(div.rhythm-tag)'):
        link = tag.get("href")
        name_tag = tag.select_one("div.rhythm-tag > h2")

        if link and "/genre/v/" in link and name_tag:
            genres.append({
                "link": urljoin(BASE_URL, link),
                "name": name_tag.text.strip()
            })

    return genres

def get_song_links(genre_url):
    song_links = set()

    for page in range(100):
        url = f"{genre_url}?offset={page * 10}"
        content = fetch_html(url)

        if not content:
            break

        soup = BeautifulSoup(content, "html.parser")
        titles = soup.find_all("a", class_="song-title")

        if not titles:
            break

        for tag in titles:
            href = tag.get("href", "").strip()

            if href and not href.startswith("http"):
                song_links.add(urljoin(BASE_URL, href))
            elif href.startswith(BASE_URL + "/song/"):
                song_links.add(href)

    return list(song_links)

def get_song_details(url):
    try:
        content = fetch_html(url)

        if not content:
            return None

        soup = BeautifulSoup(content, "html.parser")
        title_el = soup.select_one("#song-title span")
        title = title_el.text.strip() if title_el else "No title"
        authors = [a.text.strip() for a in soup.select('#song-author .author-item')]
        author_str = " - ".join(authors) if authors else "No author"
        rhythm = soup.select_one('#display-rhythm')
        category = rhythm.text.strip() if rhythm else ""
        singer_el = soup.select_one("span.perform-singer-list a.author-item")
        singer_name = singer_el.text.strip() if singer_el else ""

        lyrics = []

        for line in soup.select('#song-lyric .chord_lyric_line'):
            if 'text_only' in line.get('class', []):
                continue

            parts = []

            for item in line.contents:
                if item.name == 'span':
                    if 'hopamchuan_chord_inline' in item.get('class', []):
                        chord = item.find('span', class_='hopamchuan_chord')

                        if chord:
                            parts.append(f'<span class="chord">[{chord.text}]</span>')
                    elif 'hopamchuan_lyric' in item.get('class', []):
                        parts.append(item.text)
                elif isinstance(item, str):
                    parts.append(item.strip())

            lyrics.append(" ".join(parts))

        return {
            'title': title,
            'content': "\n".join(lyrics),
            'author_str': author_str,
            'category': category,
            'url': url,
            'singer': singer_name
        }
    except Exception as e:
        print(f"[ERROR] get_song_details {url}: {e}")

        return None

def get_or_create_wp_category(name):
    try:
        response = requests.get(
            WP_URL_CATEGORY,
            params={"search": name},
            auth=HTTPBasicAuth(WP_USERNAME, WP_PASSWORD)
        )

        response.raise_for_status()
        data = response.json()

        if data:
            return data[0]["id"]

        response = requests.post(
            WP_URL_CATEGORY,
            json={"name": name},
            auth=HTTPBasicAuth(WP_USERNAME, WP_PASSWORD)
        )

        response.raise_for_status()
        data = response.json()

        return data["id"]
    except Exception as e:
        print(f"[ERROR] get_or_create_wp_category '{name}': {e}")

        return None

def get_or_create_wp_tag(name):
    try:
        response = requests.get(
            f"{WP_SITE_URL}/wp-json/wp/v2/tags",
            params={"search": name},
            auth=HTTPBasicAuth(WP_USERNAME, WP_PASSWORD)
        )
        response.raise_for_status()
        data = response.json()
        if data:
            return data[0]["id"]

        response = requests.post(
            f"{WP_SITE_URL}/wp-json/wp/v2/tags",
            json={"name": name},
            auth=HTTPBasicAuth(WP_USERNAME, WP_PASSWORD)
        )
        response.raise_for_status()
        return response.json()["id"]
    except Exception as e:
        print(f"[ERROR] get_or_create_wp_tag '{name}': {e}")

        return None

def post_to_wordpress(song):
    try:
        category_id = get_or_create_wp_category(song['category']) if song['category'] else None
        tag_id = get_or_create_wp_tag(song["singer"]) if song.get("singer") else None

        post_data = {
            "title": song['title'],
            "content": f"<pre>{song['content']}</pre>",
            "status": "draft",
            "categories": [category_id] if category_id else [],
            "tags": [tag_id] if tag_id else [],
        }

        response = requests.post(
            WP_URL_PUBLISH_POST,
            json=post_data,
            auth=HTTPBasicAuth(WP_USERNAME, WP_PASSWORD)
        )

        if response.status_code == 201:
            print(f"[SUCCESS] post_to_wordpress: {song['title']}")

            return True
        else:
            print(f"[ERROR] post_to_wordpress: {song['title']}, status {response.status_code}: {response.text}")

            return False
    except Exception as e:
        print(f"[ERROR] Exception: {e}")

        return False

def load_crawled_urls():
    if os.path.exists(crawled_urls_file):
        with open(crawled_urls_file, "rb") as f:
            return pickle.load(f)
        
    return set()

def save_crawled_urls(urls):
    with open(crawled_urls_file, "wb") as f:
        pickle.dump(urls, f)

def main():
    print("[STARTED] Crawling...")
    crawled_urls = load_crawled_urls()

    while True:
        genres = get_genres()
        all_links = []

        for genre in genres:
            all_links.extend(get_song_links(genre["link"]))

        for url in all_links:
            if url in crawled_urls:
                continue

            song = get_song_details(url)

            if song and post_to_wordpress(song):
                crawled_urls.add(url)
                save_crawled_urls(crawled_urls)
                time.sleep(int(DELAY_POSTING) * 60)
                break

if __name__ == "__main__":
    main()
