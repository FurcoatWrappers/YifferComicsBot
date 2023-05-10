"""
Lightweight Yiffer API wrapper for Python 3.6+

Also includes methods for generating URLs for Yiffer comics
based on the observed URL patterns.

main point is NO SELENIUM and NO BS4
requests will only be used for JSON data from API
"""

# These are the API endpoints that requests will be used for.
"""
'/api/artists'
'/api/artists/:name'
"""
"""
'/api/all-comics'
'/api/comicsPaginated'
'/api/firstComics'
'/api/comics/:name' 
"""
from typing import (
    List,
)
from datetime import datetime
from dataclasses import dataclass, field

import requests

import sqlite3
import difflib
import json
import time
import os

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), './comics.db')
BASE_URL = 'https://yiffer.xyz'
STATIC_URL = 'https://static.yiffer.xyz'
API_URL = f'{BASE_URL}/api'
THUMBNAIL_URL = f"{STATIC_URL}/comics/{{comic_name}}/thumbnail.webp"
COMICS_URL = f"{STATIC_URL}/comics/{{comic_name}}/{{page_number:03d}}.jpg"


def create_database():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    # Create comics table
    c.execute("""CREATE TABLE comics
                 (id INTEGER UNIQUE PRIMARY KEY,
                  name TEXT,
                  thumbnail TEXT,
                  category TEXT,
                  tag TEXT,
                  artist TEXT,
                  state TEXT,
                  created TIMESTAMP,
                  updated TIMESTAMP,
                  userRating REAL)""")

    # Create pages table
    c.execute("""CREATE TABLE pages
                 (comic_name TEXT,
                  page_number INTEGER,
                  page_url TEXT,
                  FOREIGN KEY (comic_name) REFERENCES comics(name))""")

    # Create keywords table
    c.execute("""CREATE TABLE keywords
                 (comic_id INTEGER,
                  keyword TEXT,
                  FOREIGN KEY (comic_id) REFERENCES comics(id))""")

    conn.commit()
    conn.close()


@dataclass
class BasicComicData:
    # Data returned from 'api/all-comics'
    id: int
    name: str
    category: str
    tag: str
    artist: str
    updated: datetime
    state: str # 'finished', 'wip', 'cancelled'
    created: datetime
    numberOfPages: int


@dataclass
class DetailedComicData:
    # data returned from 'api/comics/:name'
    name: str
    numberOfPages: int
    artist: str
    id: int
    category: str
    tag: str
    created: datetime
    updated: datetime
    rating: float = None
    keywords: List[str] = field(default_factory=list)


@dataclass
class ComicData:
    # Combine BasicComicData and DetailedComicData
    id: int
    name: str
    thumbnail: str
    numberOfPages: int
    artist: str
    category: str
    tag: str
    created: datetime
    updated: datetime
    state: str
    userRating: float = None
    keywords: List[str] = field(default_factory=list)
    pages: List[str] = field(default_factory=list) # Our own list of pages

    def save_to_db(self):
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()

        # Save comic details to the comics table
        c.execute("""INSERT INTO comics (id, name, thumbnail, category, tag, artist, state, created, updated, userRating)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (self.id, self.name, self.thumbnail, self.category, self.tag, self.artist, self.state, self.created, self.updated, self.userRating))

        # Save pages to the pages table
        for i, page_url in enumerate(self.pages, 1):
            c.execute("INSERT INTO pages (comic_name, page_number, page_url) VALUES (?, ?, ?)", (self.name, i, page_url))

        # Save keywords to the keywords table
        for keyword in self.keywords:
            c.execute("INSERT INTO keywords (comic_id, keyword) VALUES (?, ?)", (self.id, keyword))

        conn.commit()
        conn.close()

    @classmethod
    def from_basic_and_detailed(cls, basic: BasicComicData, detailed: DetailedComicData):
        return cls(
            id=basic.id,
            name=basic.name,
            thumbnail=get_comic_thumbnail_by_name(basic.name),
            numberOfPages=basic.numberOfPages,
            artist=basic.artist,
            category=basic.category,
            tag=basic.tag,
            created=basic.created,
            updated=basic.updated,
            state=basic.state,
            userRating=detailed.rating,
            keywords=detailed.keywords,
            pages=get_comic_pages_by_name_and_pages(basic.name, basic.numberOfPages)
        )
    
    @classmethod
    def load_from_db(cls, comic_name: str):
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()

        # Retrieve comic data from the comics table
        c.execute("SELECT * FROM comics WHERE name=?", (comic_name,))
        comic_data = c.fetchone()

        # Retrieve pages from the pages table
        c.execute("SELECT page_url FROM pages WHERE comic_name=? ORDER BY page_number", (comic_name,))
        pages = [row[0] for row in c.fetchall()]

        # Retrieve keywords from the keywords table
        c.execute("SELECT keyword FROM keywords WHERE comic_id=?", (comic_data[0],))
        keywords = [row[0] for row in c.fetchall()]

        conn.close()

        # Build FullComicData object
        return cls(
            id=comic_data[0],
            name=comic_data[1],
            thumbnail=comic_data[2],
            category=comic_data[3],
            numberOfPages=len(pages),
            tag=comic_data[4],
            artist=comic_data[5],
            state=comic_data[6],
            created=comic_data[7],
            updated=comic_data[8],
            userRating=comic_data[9],
            keywords=keywords,
            pages=pages
        )

    @staticmethod
    def search_by_keywords(keywords: List[str], limit: int = 10) -> List['ComicData']:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()

        # Use string formatting to build a query string based on the number of keywords
        query_string = "SELECT DISTINCT comic_id FROM keywords WHERE keyword IN ({})".format(", ".join("?" * len(keywords)))
        c.execute(query_string, tuple(keywords))

        # Get the top matching comic IDs
        matching_comic_ids = [row[0] for row in c.fetchall()][:limit]

        # Retrieve FullComicData objects for the top comics
        matched_comics = [ComicData.load_from_db(comic_id) for comic_id in matching_comic_ids]

        conn.close()

        return matched_comics

    @staticmethod
    def search_comics_by_name(query: str, limit: int = 10) -> List['ComicData']:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()

        # Retrieve all comic names from the comics table
        c.execute("SELECT name FROM comics")
        all_comics = c.fetchall()

        # Find the top 10 closest matching comic names
        closest_matches = difflib.get_close_matches(query.title(), [comic[0] for comic in all_comics], n=limit, cutoff=0.3)

        if not closest_matches:
            return []

        # Retrieve ComicData objects for the closest matches
        matched_comics = []
        for comic_name in closest_matches:
            matched_comics.append(ComicData.load_from_db(comic_name))

        conn.close()

        return matched_comics

    @staticmethod
    def search_comics_by_artist(query: str, limit: int = 10) -> List['ComicData']:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()

        # Retrieve all comic artists from the comics table
        c.execute("SELECT id, artist FROM comics")
        all_comics = c.fetchall()

        # Find the top 10 closest matching comic artists
        closest_matches = difflib.get_close_matches(query, [comic[1] for comic in all_comics], n=limit)

        # Retrieve ComicData objects for the closest matches
        matched_comics = []
        for comic_artist in closest_matches:
            comic_id = next((comic[0] for comic in all_comics if comic[1] == comic_artist), None)
            if comic_id:
                matched_comics.append(ComicData.load_from_db(comic_id))

        conn.close()

        return matched_comics
    
    @staticmethod
    def search_comics_by_category(query: str, limit: int = 10) -> List['ComicData']:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()

        # Retrieve all comic categories from the comics table
        c.execute("SELECT id, category FROM comics")
        all_comics = c.fetchall()

        # Find the top 10 closest matching comic categories
        closest_matches = difflib.get_close_matches(query, [comic[1] for comic in all_comics], n=limit)

        # Retrieve ComicData objects for the closest matches
        matched_comics = []
        for comic_category in closest_matches:
            comic_id = next((comic[0] for comic in all_comics if comic[1] == comic_category), None)
            if comic_id:
                matched_comics.append(ComicData.load_from_db(comic_id))

        conn.close()

        return matched_comics
    
    @staticmethod
    def search_comics_by_tag(query: str, limit: int = 10) -> List['ComicData']:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()

        # Retrieve all comic tags from the comics table
        c.execute("SELECT id, tag FROM comics")
        all_comics = c.fetchall()

        # Find the top 10 closest matching comic tags
        closest_matches = difflib.get_close_matches(query, [comic[1] for comic in all_comics], n=limit)

        # Retrieve ComicData objects for the closest matches
        matched_comics = []
        for comic_tag in closest_matches:
            comic_id = next((comic[0] for comic in all_comics if comic[1] == comic_tag), None)
            if comic_id:
                matched_comics.append(ComicData.load_from_db(comic_id))

        conn.close()

        return matched_comics
    
    @staticmethod
    def search_comics_by_page(page: int, limit: int = 10) -> List['ComicData']:
        # Order by the comic ID then offset by the page number
        offset = (page - 1) * limit
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()

        # Retrieve the comic IDs for the page
        c.execute("SELECT name FROM comics ORDER BY userRating DESC LIMIT ? OFFSET ?", (limit, offset))
        comic_names = [row[0] for row in c.fetchall()]

        # Retrieve ComicData objects for the closest matches
        matched_comics = []
        for name in comic_names:
            matched_comics.append(ComicData.load_from_db(name))

        conn.close()

        return matched_comics
    
    @staticmethod
    def get_max_page_number() -> int:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()

        # Retrieve the number of comics
        c.execute("SELECT COUNT(*) FROM comics")
        number_of_comics = c.fetchone()[0]

        conn.close()

        return round((number_of_comics - 1) / 10)

def update_db():
    start = time.perf_counter()
    # Go through each comic and add it to the database
    # Then retrieve individual comic for additional info

    # Get JSON of every single comic
    comics = get_all_comics()

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    comics_new_pages = []

    # Loop over each comic
    for basic_comic_data in comics:

        # Get the name of the comic
        name = basic_comic_data.name

        # Get any pages we may have
        c.execute("""SELECT * FROM pages WHERE comic_name=?""", (name,))
        existing_pages = c.fetchall()

        # If we don't have any pages, or we don't have enough pages, add the comic to the database
        if (len(existing_pages) < basic_comic_data.numberOfPages):
            detailed_comic_data = get_comic_data_by_name(name)

            comic_data = ComicData.from_basic_and_detailed(basic_comic_data, detailed_comic_data)
            comic_data.save_to_db()

            comics_new_pages.append(f"{name} ({len(existing_pages)} -> {comic_data.numberOfPages})")

        conn.commit()

    if comics_new_pages:
        new_pages = '\n\t'.join(comics_new_pages)
        print(f"New comics:\n{new_pages}")

    print(f"Updated {len(comics_new_pages)} new comics in {(time.perf_counter() - start):.2f} seconds.")


def get_comic_thumbnail_by_name(name: str) -> str:
    """
    Gets a URL for a comic thumbnail by name.
    :param name: Name of comic
    :return: URL for comic thumbnail
    """
    return THUMBNAIL_URL.format(comic_name=name.replace(' ', '%20'))


def get_comic_page_by_name_and_page(name: str, page: int) -> str:
    """
    Gets a URL for a comic page by name and page number.
    :param name: Name of comic
    :param page: Page number
    :return: URL for comic page
    """
    return COMICS_URL.format(comic_name=name.replace(' ', '%20'), page_number=page)


def get_comic_pages_by_name_and_pages(name: str, pages: int) -> List[str]:
    """
    Gets a list of URLs for comic pages by name and number of pages.
    :param name: Name of comic
    :param pages: Number of pages in comic
    :return: List of URLs for comic pages
    """
    image_urls = []
    for i in range(1, pages + 1):
        url = COMICS_URL.format(comic_name=name.replace(' ', '%20'), page_number=i)
        image_urls.append(url)

    return image_urls


def get_comic_data_by_name(name: str) -> DetailedComicData:
    """
    Gets a comic's data by name.
    :param name: Name of comic
    :return: Comic data
    """
    url = f"{API_URL}/comics/{name}"
    response = requests.get(url)
    if response.status_code == 200:
        data = json.loads(response.text)
        comic_data = {
            'name': data['name'],
            'numberOfPages': data['numberOfPages'],
            'artist': data['artist'],
            'id': data['id'],
            'category': data['cat'],
            'tag': data['tag'],
            'created': data['created'],
            'updated': data['updated'],
            'rating': data['userRating'],
            'keywords': data['keywords'],
        }
        return DetailedComicData(**comic_data)
    else:
        return None
    

def get_all_comics() -> List[BasicComicData]:
    """
    Gets all comics.
    :return: All comics
    """
    url = f'{API_URL}/all-comics'
    response = requests.get(url)
    if response.status_code == 200:
        all_comic_data = json.loads(response.text)
        comics = []
        for data in all_comic_data:
            comic_data = {
                'id': data['id'],
                'name': data['name'],
                'category': data['cat'],
                'tag': data['tag'],
                'artist': data['artist'],
                'updated': data['updated'],
                'state': data['state'],
                'created': data['created'],
                'numberOfPages': data['numberOfPages'],
            }
            comics.append(BasicComicData(**comic_data))
        return comics
    else:
        return None

   
def get_all_comics_full() -> List[ComicData]:
    """
    Gets all comics.
    :return: All comics
    """
    url = f'{API_URL}/all-comics'
    response = requests.get(url)
    if response.status_code == 200:
        return [ComicData.from_basic_and_detailed(BasicComicData(**comic), get_comic_data_by_name(comic['name'])) for comic in json.loads(response.text)]
    else:
        return None


# Test the wrapper above:
def main():
    if not os.path.exists(DATABASE):
        print('Database does not exist. Creating...')
        create_database()
    update_db()


if __name__ == "__main__":
    main()