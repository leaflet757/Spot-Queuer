from datetime import date
from datetime import datetime
import json
import os, os.path
import tekore as tk
import sys
import time


# Example usage:
# python src\spot-queuer.py <user.data> <lastrun> [options]
# 
# [options]
# -a : scan artists
# -p : scan playlists
# -d <date> : overwrite last run date, "year-month-day"
# -fp : print followed playlists
#
# Running this will open up a webbrowser window asking to allow the script access of your Spotify
# account. Scroll all the way to the bottom without reading any of the TOS and click the accept
# button. This will open a new page to example.com. Copy the entire URL of this page and paste
# it into the terminal window.
#
# The <user.data> file must be in JSON format and be of the form:
# {
#     "user":
#     {
#         "client_id":"xxxxxxxxxx",
#         "client_secret":"xxxxxxxxxxx",
#         "redirect_uri":"https://example.com/callback",
#         "listen_later":"xxxxxxxxxx"
#     },
#     "playlists":
#     [  
#         {
#             "name":"Human Music Playlist",
#             "id":"xxxxxxxxxx",
#             "limit":"-1"
#         },
#     ]
# }

# TODO:
# display stale playlists
# Server Error 500
# check for track dups
# pick top rated songs from playlists
# sort sets into separate playlist
# clean up this shitty code

####################################################
#..................... Types ......................#
####################################################

class Config():
    def __init__(self):
        self.TRACK_LIMIT = 20
        self.ARTIST_LIMIT = 50
        self.ALBUM_LIMIT = 50
        self.PLAYLIST_LIMIT = 100
        self.MARKET = "US"
        self.DATE_FORMAT = "%Y-%m-%d"
        self.today_date = date.today()
        self.last_run_date = date(2021,1,1)
        self.scan_artists = False
        self.scan_playlists = False
        self.show_followed_playlists = False
        self.client_id = ""
        self.client_secret = ""
        self.redirect_uri = ""
        self.listen_later = ""
        self.last_run_path = ""
        self.playlist_meta = dict()
    def __str__(self):
        return f'Config({self.client_id},{self.redirect_uri})'

class Cache:
    def __init__(self):
        self.track_datas = list()
        self.track_datas_map = dict() #id, index
        self.album_datas = list()
        self.album_datas_map = dict() #id, index
        self.playlist_datas = list()
        self.playlist_datas_map = dict() #id, index

class Playlist:
    def __init__(self):
        self.name = ""
        self.id = ""
        self.limit = 0
        self.tracks = list()
    def __str__(self):
        return f'Playlist({self.name},{self.id},{self.limit})'
    def Unbounded(self):
        return self.limit == -1
    def total_tracks(self):
        return len(self.tracks)

class Album:
    def __init__(self):
        self.name = ""
        self.id = ""
        self.artist_id = ""
        self.release_date = date(2021,1,1)
        self.tracks = list()
    def __str__(self):
        return f'Album({self.name},{self.id})'
    def total_tracks(self):
        return len(self.tracks)

class Track:
    def __init__(self):
        self.uri = ""
        self.name = ""
        self.artist = -1
        self.album = -1
        self.playlist = -1
        self.score = 0
        self.datetime = datetime()
    def __str__(self):
        return f'Track({self.name} by {self.artist})'

####################################################
#.................. API Functions .................#
####################################################

def print_all_playlists(spotify):
    print('----------Printing Followed Playlists----------')
    current_user = spotify.current_user()
    playlist_chunk = spotify.playlists(current_user.id, 20)
    last_playlist = 0
    while len(playlist_chunk.items) > 0:
        for playlist in playlist_chunk.items:
            print(playlist.name, playlist.id)
        last_playlist += len(playlist_chunk.items)
        playlist_chunk = spotify.playlists(current_user.id, 20, offset=last_playlist)
    print('-----------------------------------------------')
    exit()

def add_to_listen_to_later(spotify, to_add_tracks, listen_later, PLAYLIST_LIMIT):
    last_chunk_track_index = 0
    to_add_track_length = len(to_add_tracks)
    print('Found', to_add_track_length, 'new tracks. Adding tracks to playlist...')
    # we know there is at least 1 item to add
    last_item = min(to_add_track_length, PLAYLIST_LIMIT)
    
    num_added = 0
    while last_chunk_track_index < last_item:
        #print('index:', last_chunk_track_index, 'last:', last_item)
        track_chunk = to_add_tracks[last_chunk_track_index:last_item]
        print('Adding tracks', last_chunk_track_index, 'through', last_item)
        while True: # TODO boo
            try:
                spotify.playlist_add(listen_later, track_chunk)
                break
            except tk.TooManyRequests as err:
                sleep_amount = int(err.response.headers['retry-after'])
                retry_sleep(sleep_amount)
        num_added += len(track_chunk)
        last_chunk_track_index = last_item
        last_item += min(to_add_track_length - last_item, PLAYLIST_LIMIT)
    
    return num_added

def check_last_run_quit(conf):
    if conf.today_date <= conf.last_run_date:
        print('Already ran Spot-Queuer today. Smallest API precision is Day, exiting early.')
        exit()

def scan_artist_tracks(spotfiy, conf, cache, to_add_tracks, error_artists, error_albums):
    to_add_albums = list()
    all_artists = list()

    last_chunk_album_index = 0
    last_chunk_track_index = 0
    last_chunk_artist_id = ''
    
    followed_artists = spotify.followed_artists(limit=conf.ARTIST_LIMIT)
    
    while len(followed_artists.items) > 0:
        for artist in followed_artists.items:
            print('>>>%s' % artist.name)
            all_artists.append(artist.id)
            
            while True:
                try:
                    artist_albums = spotify.artist_albums(artist_id=artist.id, market=conf.MARKET, limit=conf.ALBUM_LIMIT)
                    break # TODO booo
                except tk.TooManyRequests as err:
                    sleep_amount = int(err.response.headers['retry-after'])
                    retry_sleep(sleep_amount)
            
            last_chunk_album_index = 0
            
            while len(artist_albums.items) > 0:
                for album in artist_albums.items:
                    # increment the index regardless if we can add the album
                    album_date_split = album.release_date.split('-')
                    
                    if len(album_date_split) != 3:
                        if len(album_date_split) == 1:
                            #print('  -%s date set to %s-1-1' % (album.name, album.release_date))
                            album_date = date(int(album_date_split[0]), 1, 1)
                        else:
                            print('  !%s date %s could not be determined' % (album.name, album.release_date))
                            # Check if this artist already has problems
                            if len(error_artists) == 0 or error_artists[-1][0] != artist.name:
                                # add problem artist
                                error_artists.append((artist.name, list()))
                            error_artists[-1][1].append(len(error_albums))
                            error_albums.append(album.name)
                            continue
                    else:
                        album_date = date(int(album_date_split[0]), int(album_date_split[1]), int(album_date_split[2]))
                    
                    # Create the Album Data
                    albumData = Album()
                    albumData.name = album.name
                    albumData.id = album.id
                    albumData.total_tracks = album.total_tracks
                    albumData.release_date = album_date
                    albumData.artist_id = artist.id
                    
                    # Add Album to cache
                    albumDataIndex = len(cache.album_datas)
                    cache.album_datas_map[album.id] = albumDataIndex
                    cache.album_datas.append(albumData)

                    if albumData.release_date >= conf.last_run_date:
                        print('  *%s queueing' % (albumData.name))
                        to_add_albums.append(albumDataIndex)
                    

                last_chunk_album_index += len(artist_albums.items)
                #print('last chunk', last_chunk_album_index, 'num itesm', len(artist_albums.items))

                while True: # TODO boooo
                    try:
                        artist_albums = spotify.artist_albums(artist_id=artist.id, market=conf.MARKET, limit=conf.ALBUM_LIMIT, offset=last_chunk_album_index)
                        break
                    except tk.TooManyRequests as err:
                        sleep_amount = int(err.response.headers['retry-after'])
                        retry_sleep(sleep_amount)

        last_chunk_artist_id = followed_artists.items[-1].id

        while True: # TODO boo
            try:
                followed_artists = spotify.followed_artists(limit=conf.ARTIST_LIMIT, after=last_chunk_artist_id)
                break
            except tk.TooManyRequests as err:
                sleep_amount = int(err.response.headers['retry-after'])
                retry_sleep(sleep_amount)

    to_add_length = len(to_add_albums)
    print('Artist scan complete. Found', to_add_length, 'new albums.')

    # Now cull any artist tracks that are not the ones we follow
    if to_add_length > 0:
        print('Finding album tracks...')
        
        album_count = 0
        for album_index in to_add_albums:
            album_data = cache.album_datas[album_index]
            album_id = album_data.id
            album_track_num = album_data.total_tracks
            target_artist_id = album_data.artist_id
            last_chunk_track_index = 0

            album_count += 1
            if album_count % 50 == 1:
                print('Processing album chunk', album_count, 'of', to_add_length)
            
            while last_chunk_track_index < album_track_num:
                while True: # TODO boo
                    try:
                        tracks = spotify.album_tracks(album_id, market=conf.MARKET, limit=conf.TRACK_LIMIT, offset=last_chunk_track_index)
                        break
                    except tk.TooManyRequests as err:
                        sleep_amount = int(err.response.headers['retry-after'])
                        retry_sleep(sleep_amount)
                for track in tracks.items:
                    shouldAdd = False
                    for track_artist in track.artists:
                        if track_artist.id == target_artist_id:
                            shouldAdd = True
                    if shouldAdd:
                        print('*%s by %s' % (track.name, track_artist.name))
                        to_add_tracks.append(track.uri)
                        logs_artist_tracks.append(('%s - %s' % (track_artist.name, track.name)).encode('utf8'))
                last_chunk_track_index += len(tracks.items)

def scan_followed_playlists(spotify, conf):
    last_run_dt = datetime.combine(conf.last_run_date, datetime.min.time())
    for playlist_id, meta in conf.playlist_meta.items():
        last_chunk_track_index = 0
        while True:
            try:
                playlist_full = spotify.playlist(playlist_id, market=conf.MARKET)
                playlist_tracks = spotify.playlist_items(playlist_id, market=conf.MARKET, limit=conf.PLAYLIST_LIMIT)
                break
            except tk.TooManyRequests as err:
                sleep_amount = int(err.response.headers['retry-after'])
                retry_sleep(sleep_amount)
        print('>>>%s' % playlist_full.name)
        added_count = 0
        while len(playlist_tracks.items) > 0 and (added_count < meta.limit or meta.Unbounded()):
            for playlist_track in playlist_tracks.items:
                if not (added_count < meta.limit or meta.Unbounded()):
                    print('hit limit for', meta.name)
                    break
                # playlist_track.track.popularity
                if playlist_track.added_at >= last_run_dt:
                    print('  *%s queueing' % playlist_track.track.name)
                    # Comment line below to not add playlist tracks
                    to_add_tracks.append(playlist_track.track.uri)
                    added_count += 1
                    logs_playlist_tracks.append(('%s - %s' % (playlist_full.name, playlist_track.track.name)).encode('utf8'))
            last_chunk_track_index += len(playlist_tracks.items)
            while True: # TODO booo
                try:
                    playlist_tracks = spotify.playlist_items(playlist_id, market=conf.MARKET, limit=conf.PLAYLIST_LIMIT, offset=last_chunk_track_index)
                    break
                except tk.TooManyRequests as err:
                    sleep_amount = int(err.response.headers['retry-after'])
                    retry_sleep(sleep_amount)

####################################################
#..................... Utility ......................#
####################################################

def check_optional_arg(index, argv, conf):
    if argv[index] == '-a':
        conf.scan_artists = True
    elif argv[index] == '-p':
        conf.scan_playlists = True
    elif argv[index] == '-fp':
        conf.show_followed_playlists = True
    elif argv[index] == '-d':
        newDate = parse_date_string(argv[index + 1])
        print('Overwriting last run date %s. Writing new date %s' % (conf.last_run_date, newDate))
        conf.last_run_date = newDate

def parse_date_string(date_str):
    # If the date format is changed the return might need updating    
    #today = date(2011, 1, 1)
    date_split = date_str.split('-')
    return date(int(date_split[0]), int(date_split[1]), int(date_split[2]))

def init_last_run(conf):
    f = open(conf.last_run_path,"r")
    conf.last_run_date = parse_date_string(f.read())
    f.close()
    
def set_last_run(conf):
    today = date.today()
    date_str = today.strftime(conf.DATE_FORMAT)
    print('Last run was on %s. Writing new date %s' % (conf.last_run_date, date_str))
    f = open(conf.last_run_path,"w")
    f.write(date_str)
    f.close()

def init_config(user_data_path, last_run_path):
    print('Loading User Config', user_data_path)
    
    c = Config()
    f = open(user_data_path, 'r')
    
    j = json.load(f)
    
    # User configuration
    user = j['user']
    c.client_id = user['client_id']
    c.client_secret = user['client_secret']
    c.redirect_uri = user['redirect_uri']
    c.listen_later = user['listen_later']
    c.last_run_path = last_run_path

    # playlist configuration
    for playlist_info in j['playlists']:
        meta = Playlist()
        meta.id = playlist_info['id']
        meta.name = playlist_info['name']
        meta.limit = int(playlist_info['limit'])
        c.playlist_meta[meta.id] = meta
    
    f.close()
    
    print('Loaded User Config', c)
    return c

def write_logs(artist_tracks, playlist_tracks, run_date):
    #num_items = len([name for name in os.listdir('C:/Users/lemyer/dev/Spot-Queuer/Spot-Queuer/logs/') if os.path.isfile(name)])
    #filename = "C:/Users/lemyer/dev/Spot-Queuer/Spot-Queuer/logs/info%d.log" % (num_items + 1)
    f = open('info.log',"w")
    f.write("Date: %s\n" % run_date)
    if len(artist_tracks) > 0:
        f.write("--------------------------------\n")
        f.write("Artist Tracks:\n")
        for item in artist_tracks:
            f.write("%s\n" % item)
    if len(playlist_tracks) > 0:
        f.write("--------------------------------\n")
        f.write("Playlist Tracks:\n")
        for item in playlist_tracks:
            f.write("%s\n" % item)
    f.close()

def retry_sleep(num_seconds):
    print('Spotfiy rate limit hit. Retry in', num_seconds, 'seconds.')
    time.sleep(num_seconds)

####################################################
#........................MAIN......................#
####################################################

# Get Arguments
assert(len(sys.argv) >= 3)
user_data_path = sys.argv[1]
last_run_path = sys.argv[2]

# Load User Config
conf = init_config(user_data_path, last_run_path)

# Get Last Run Date
init_last_run(conf)

# Load Options
for i in range(3, len(sys.argv)):
    check_optional_arg(i, sys.argv, conf)

# Load Spotify
token = tk.prompt_for_user_token(conf.client_id, conf.client_secret, conf.redirect_uri, scope=tk.scope.every)
spotify = tk.Spotify(token)

# Display followed playlist IDs and exit
if conf.show_followed_playlists:
    print_all_playlists(spotify)

# Quit if we already ran today
check_last_run_quit(conf)

print('Authentication complete.')

# Cached Data
cache = Cache()

# List of Tracks IDs that will be added to the watch later playlist
to_add_tracks = list()

# Logs
logs_artist_tracks = list()
logs_playlist_tracks = list()
error_artists = list() #index0: artistname, index1: album index list
error_albums = list()

# Scan Followed Artists
if conf.scan_artists:
    scan_artist_tracks(spotify, conf, cache, to_add_tracks, error_artists, error_albums)
    
# Scan Specified Playlists
if len(conf.playlist_meta.values()) > 0 and conf.scan_playlists:
    scan_followed_playlists(spotify, conf)

# If there were any tracks found that were new, add them to our playlist
num_added = 0
if len(to_add_tracks) > 0:
    num_added = add_to_listen_to_later(spotify, to_add_tracks, conf.listen_later, conf.PLAYLIST_LIMIT)

# We're done here, now store when we last ran
set_last_run(conf)

print('Spot-Queuer Finished. Added', num_added, 'new songs.')

if len(error_albums) > 0:
    print('Spot-Queuer ran with errors :(\nCould not find release information for:')
    assert(len(error_albums) > 0 and len(error_artists) > 0)
    for artistPair in error_artists:
        print(artistPair[0])
        for index in artistPair[1]:
            print('  -%s' % error_albums[index])

if len(logs_artist_tracks) > 0 or len(logs_playlist_tracks) > 0:
    write_logs(logs_artist_tracks, logs_playlist_tracks, conf.last_run_date)