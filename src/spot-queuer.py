from datetime import date
from datetime import datetime
import json
import os, os.path
import tekore as tk
import random
import sys
import time

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
        self.last_run_date_artist = date(2021,1,1)
        self.last_run_date_playlist = date(2021,1,1)
        self.scan_artists = False
        self.scan_playlists = False
        self.show_followed_playlists = False
        self.client_id = ""
        self.client_secret = ""
        self.redirect_uri = ""
        self.last_run_path = ""
        self.logs_path = ""
        self.listen_later = ""
        self.sets = ""
        self.compilations = ""
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
        self.artist_datas = list()
        self.artist_datas_map = dict() #id, index

class AlbumAdder:
    def __init__(self):
        self.listen_later = list()
        self.sets = list()
        self.compilations = list()
    def has_tracks(self):
        return len(self.listen_later) > 0 or len(self.sets) > 0 or len(self.compilations) > 0

class Artist:
    def __init__(self):
        self.name = ""
        self.id = ""
        self.tracks = list()
    def __str__(self):
        return f'Artist({self.name},{self.id},{len(self.tracks)})'

class Playlist:
    def __init__(self):
        self.name = ""
        self.id = ""
        self.limit = 0
        self.tracks = list()
    def __str__(self):
        return f'Playlist({self.name},{self.id},{self.limit},{len(self.tracks)})'
    def Unbounded(self):
        return self.limit == -1
    def total_tracks(self):
        return len(self.tracks)

class Album:
    def __init__(self):
        self.name = ""
        self.id = ""
        self.type = ""
        self.artist_id = -1
        self.release_date = date(2021,1,1)
        self.tracks = list()
    def __str__(self):
        return f'Album({self.name},{self.id})'
    def total_tracks(self):
        return len(self.tracks)
    def is_comp(self):
        return self.type == 'compilation'
    def is_album(self):
        return self.type == 'album'
    def is_single(self):
        return self.type == 'single'

class Track:
    def __init__(self):
        self.uri = ""
        self.name = ""
        self.artist = -1
        self.album = -1
        self.playlist = -1
        self.score = 0
        self.datetime = datetime.min.time()
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
    shuffle_tracks = to_add_tracks.copy()
    # shuffle da tracks
    random.shuffle(shuffle_tracks)
    to_add_track_length = len(shuffle_tracks)
    print('Found', to_add_track_length, 'new tracks. Adding tracks to playlist...')
    # we know there is at least 1 item to add
    last_item = min(to_add_track_length, PLAYLIST_LIMIT)
    
    num_added = 0
    while last_chunk_track_index < last_item:
        track_chunk = shuffle_tracks[last_chunk_track_index:last_item]
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

def check_last_run_quit(today, last_run):
    if today <= last_run:
        print('Already ran Spot-Queuer today. Smallest API precision is Day, exiting early.')
        exit()

def scan_artist_tracks(spotfiy, conf, cache, adder, logs_artist_tracks):
    to_add_albums = list()
    last_chunk_album_index = 0
    last_chunk_track_index = 0
    num_artist_tracks = 0
    last_chunk_artist_id = ''
    
    print('Finding album tracks...')
    followed_artists = spotify.followed_artists(limit=conf.ARTIST_LIMIT)
    
    while len(followed_artists.items) > 0:
        for artist in followed_artists.items:            
            print('>>>%s' % artist.name)
            
            # Create the artist if it doesn't exist
            if not artist.id in cache.album_datas_map:
                artistData = Artist()
                artistData.id = artist.id
                artistData.name = artist.name
                cache.artist_datas_map[artist.id] = len(cache.artist_datas)
                cache.artist_datas.append(artistData)
                #print('ArtistDataCount:', len(cache.artist_datas))
            
            # Get Artist albums at offset=0
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
                    
                    # Some 'Compilation' spotify albums will be marked as compilation
                    # even though we really want them in listen later playlist. But 
                    # some compilations are actual compilations of many artists. So if
                    # this album has a bunch of artists, its most likely a compilation.
                    # This will probably skip cool older songs tho :'(
                    if album.album_group == 'appears_on':
                        continue

                    # Parse Date Str
                    album_date_split = album.release_date.split('-')
                    if len(album_date_split) != 3:
                        if len(album_date_split) == 1:
                            album_date = date(int(album_date_split[0]), 1, 1)
                        else:
                            print('  !%s date %s could not be determined' % (album.name, album.release_date))
                            continue
                    else:
                        album_date = date(int(album_date_split[0]), int(album_date_split[1]), int(album_date_split[2]))

                    if album_date >= conf.last_run_date_artist:
                        # Create the Album Data
                        album_data = Album()
                        album_data.name = album.name
                        album_data.id = album.id
                        album_data.total_tracks = album.total_tracks
                        album_data.release_date = album_date
                        album_data.type = album.album_type
                        assert(artist.id in cache.artist_datas_map)
                        album_data.artist_id = cache.artist_datas_map[artist.id]
                        
                        # Add Album to cache
                        albumDataIndex = len(cache.album_datas)
                        cache.album_datas_map[album.id] = albumDataIndex
                        cache.album_datas.append(album_data)
                        #print('AlbumDataCount:', len(cache.album_datas))
                        
                        print('  *%s queueing' % (album_data.name))
                        to_add_albums.append(albumDataIndex)
                    

                last_chunk_album_index += len(artist_albums.items)

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

    # Some album tracks are released by artists we dont follow, so cull the ones we aren't following
    if to_add_length > 0:
        
        album_count = 0
        for album_index in to_add_albums:
            
            album_data = cache.album_datas[album_index]
            artist_data = cache.artist_datas[album_data.artist_id]

            target_artist_id = artist_data.id
            last_chunk_track_index = 0

            album_count += 1
            if album_count % 50 == 1:
                print('Processing album chunk', album_count, 'of', to_add_length)
            
            while last_chunk_track_index < album_data.total_tracks:
                
                while True: # TODO boo
                    try:
                        tracks = spotify.album_tracks(album_data.id, market=conf.MARKET, limit=conf.TRACK_LIMIT, offset=last_chunk_track_index)
                        break
                    except tk.TooManyRequests as err:
                        sleep_amount = int(err.response.headers['retry-after'])
                        retry_sleep(sleep_amount)
                
                for track in tracks.items:
                    
                    # Some Artists will release radio shows in an album. Sometimes we want to hear those 
                    # artists we dont follow. This 'should' be ok now that we're skipping 'appears on' albums
                    hasArtist = True
                    #hasArtist = False
                    #for track_artist in track.artists:
                    #    if track_artist.id == target_artist_id:
                    #        hasArtist = True

                    # Skip tracks that are 'intro' tracks that dont really have much music content
                    # 80s = 80000ms
                    if track.duration_ms <= 80000:
                        continue
                    
                    if hasArtist and not track.uri in cache.artist_datas_map:
                        print('  *%s by %s adding' % (track.name, artist_data.name))
                        
                        # Create the Track and add to Album
                        track_data = Track()
                        track_data.artist = album_data.artist_id
                        track_data.name = track.name
                        track_data.uri = track.uri
                        track_data.album = album_index
                        track_data.playlist = -1 # not from playlist
                        #track_data.score = track.popularity Error: SimpleTrack object has no attr 'popularity'
                        #track_data.datetime = xx # is this needed?

                        # Add track to the map
                        cache.track_datas_map[track.uri] = len(cache.track_datas)
                        cache.track_datas.append(track_data)
                        #print('TrackDataCount:', len(cache.track_datas))
                        
                        # Add all artist tracks to the 'to add' list
                        num_artist_tracks += 1

                        # Find the Playlist to add it to
                        if track.duration_ms >= 1860000: # 31 mins
                            adder.sets.append(track.uri)
                        else:
                            adder.listen_later.append(track.uri)

                        logs_artist_tracks.append(('%s -- %s -- %s' % (artist_data.name, album_data.name, track.name)).encode('utf8'))
                
                last_chunk_track_index += len(tracks.items)
    
    return num_artist_tracks

def scan_followed_playlists(spotify, conf, cache, adder, logs_playlist_tracks):
    
    sort_playlist_tracks = list()

    # Get the datetime of the current day
    last_run_dt = datetime.combine(conf.last_run_date_playlist, datetime.min.time())
    
    for i in range(len(cache.playlist_datas)):
        sort_playlist_tracks.clear()
        playlist_data = cache.playlist_datas[i]
        last_chunk_track_index = 0

        while True:
            try:
                playlist_full = spotify.playlist(playlist_data.id, market=conf.MARKET)
                playlist_tracks = spotify.playlist_items(playlist_data.id, market=conf.MARKET, limit=conf.PLAYLIST_LIMIT)
                break
            except tk.TooManyRequests as err:
                sleep_amount = int(err.response.headers['retry-after'])
                retry_sleep(sleep_amount)
        
        print('>>>%s' % playlist_full.name)

        while len(playlist_tracks.items) > 0:
            for playlist_track in playlist_tracks.items:
                
                if playlist_track.added_at >= last_run_dt and playlist_track.track.uri not in cache.playlist_datas_map:
                    
                    # Create the Track and add to Album
                    track_data = Track()
                    track_data.artist = -1
                    track_data.name = playlist_track.track.name
                    track_data.uri = playlist_track.track.uri
                    track_data.album = -1
                    track_data.playlist = i
                    track_data.score = playlist_track.track.popularity
                    #track_data.datetime = xx # is this needed?
                    
                    # Queue up the Playlist Track
                    #to_add_tracks.append(playlist_track.track.uri)
                    sort_playlist_tracks.append(len(cache.track_datas))

                    # Add track to the map
                    cache.track_datas_map[track_data.uri] = len(cache.track_datas)
                    cache.track_datas.append(track_data)
                    #print('TrackDataCount:', len(cache.track_datas))
            
            last_chunk_track_index += len(playlist_tracks.items)
            
            while True: # TODO booo
                try:
                    playlist_tracks = spotify.playlist_items(playlist_data.id, market=conf.MARKET, limit=conf.PLAYLIST_LIMIT, offset=last_chunk_track_index)
                    break
                except tk.TooManyRequests as err:
                    sleep_amount = int(err.response.headers['retry-after'])
                    retry_sleep(sleep_amount)

        # Now Sort the tracks with the best score
        added_count = 0
        sort_playlist_tracks.sort(key=lambda t: cache.track_datas[t].score, reverse=True)
        for item in sort_playlist_tracks:
            if not (added_count < playlist_data.limit or playlist_data.Unbounded()):
                print('!!!Hit limit %d for %s' % (playlist_data.limit, playlist_data.name))
                break
            td = cache.track_datas[item]
            print('  *%s adding' % td.name)
            adder.listen_later.append(td.uri)
            added_count += 1
            logs_playlist_tracks.append(('%s - %s' % (playlist_data.name, td.name)).encode('utf8'))

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
        storeArtist = False
        storePlaylist = False
        for x in range(len(argv)):
            if argv[x] == '-a':
                storeArtist = True
            if argv[x] == '-p':
                storePlaylist = True
        newDate = parse_date_string(argv[index + 1])
        if storeArtist:
            print('Overwriting last run artist date %s. Writing new artist date %s.' % (conf.last_run_date_artist, newDate))
            conf.last_run_date_artist = newDate
        if storePlaylist:
            print('Overwriting last run playlist date %s. Writing new playlist date %s.' % (conf.last_run_date_playlist, newDate))
            conf.last_run_date_playlist = newDate

def parse_date_string(date_str):
    # If the date format is changed the return might need updating    
    #today = date(2011, 1, 1)
    date_split = date_str.split('-')
    return date(int(date_split[0]), int(date_split[1]), int(date_split[2]))

def init_last_run(conf):
    f = open(conf.last_run_path,"r")
    date_split = f.read().split(',')
    assert(len(date_split) == 2)
    conf.last_run_date_artist = parse_date_string(date_split[0])
    conf.last_run_date_playlist = parse_date_string(date_split[1])
    f.close()
    
def set_last_run(conf):
    today = date.today()
    date_str = today.strftime(conf.DATE_FORMAT)
    f = open(conf.last_run_path,"w")
    # write new artist date
    if conf.scan_artists:
        print('Last artist run was on %s. Writing new date %s.' % (conf.last_run_date_artist, date_str))
        f.write(date_str)
        f.write(",")
    else: # write the date from before
        f.write(conf.last_run_date_artist.strftime(conf.DATE_FORMAT))
        f.write(",")
    # write the new playlist date
    if conf.scan_playlists:
        print('Last playlist run %s. Writing new date %s.' % (conf.last_run_date_playlist, date_str))
        f.write(date_str)
    else: # write the date from before
        f.write(conf.last_run_date_playlist.strftime(conf.DATE_FORMAT))
    f.close()

def init_config(user_data_path, last_run_path, logs_path):
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
    c.compilations = user['compilation']
    c.sets = user['sets']
    c.last_run_path = last_run_path
    c.logs_path = logs_path
    
    f.close()
    
    print('Loaded User Config', c)
    return c

def init_playlist_cache(user_data_path, cache):
    print('Loading Playlist Config', user_data_path)
    
    f = open(user_data_path, 'r')
    j = json.load(f)

    # playlist configuration
    for playlist_info in j['playlists']:
        meta = Playlist()
        meta.id = playlist_info['id']
        meta.name = playlist_info['name']
        meta.limit = int(playlist_info['limit'])
        cache.playlist_datas_map[meta.id] = len(cache.playlist_datas)
        cache.playlist_datas.append(meta)
    
    f.close()

def write_logs(artist_tracks, playlist_tracks, conf):
    numfiles = len([name for name in os.listdir(conf.logs_path)])
    filename = 'info%d.log' % numfiles
    f = open(os.path.join(conf.logs_path, filename),"w")
    if len(artist_tracks) > 0:
        f.write("--------------------------------\n")
        f.write("Artist Date: %s, Total=%d\n" % (conf.last_run_date_artist, len(artist_tracks)))
        f.write("--------------------------------\n")
        for item in artist_tracks:
            f.write("%s\n" % item)
    if len(playlist_tracks) > 0:
        f.write("--------------------------------\n")
        f.write("Playlist Date: %s, Total=%d\n" % (conf.last_run_date_playlist, len(playlist_tracks)))
        f.write("--------------------------------\n")
        for item in playlist_tracks:
            f.write("%s\n" % item)
    f.close()

def retry_sleep(num_seconds):
    print('\nSpotfiy rate limit hit. Retry in', num_seconds, 'seconds.\n')
    time.sleep(num_seconds)

####################################################
#........................MAIN......................#
####################################################

# Get Arguments
# Need at least:
#   <user.data>
#   <lastrun>
#   <logfolder>
assert(len(sys.argv) >= 4)
user_data_path = sys.argv[1]
last_run_path = sys.argv[2]
logs_path = sys.argv[3]

# Load User Config
conf = init_config(user_data_path, last_run_path, logs_path)

# Get Last Run Date
init_last_run(conf)

# Load Options
for i in range(1, len(sys.argv)):
    check_optional_arg(i, sys.argv, conf)

# Load Spotify
token = tk.prompt_for_user_token(conf.client_id, conf.client_secret, conf.redirect_uri, scope=tk.scope.every)
spotify = tk.Spotify(token)

# Display followed playlist IDs and exit
if conf.show_followed_playlists:
    print_all_playlists(spotify)

print('Authentication complete.')

# Cached Data
cache = Cache()

# Load Playlist meta into Cache
init_playlist_cache(user_data_path, cache)

# List of Tracks IDs that will be added to the watch later playlist
adder = AlbumAdder()

# Logs
logs_artist_tracks = list()
logs_playlist_tracks = list()

# Scan Followed Artists
num_artist_tracks = 0
if conf.scan_artists:
    check_last_run_quit(conf.today_date, conf.last_run_date_artist)
    num_artist_tracks = scan_artist_tracks(spotify, conf, cache, adder, logs_artist_tracks)
    
# Scan Specified Playlists
num_playlist_tracks = 0
if len(cache.playlist_datas) > 0 and conf.scan_playlists:
    check_last_run_quit(conf.today_date, conf.last_run_date_playlist)
    num_playlist_tracks = scan_followed_playlists(spotify, conf, cache, adder, logs_playlist_tracks)

# If there were any tracks found that were new, add them to our playlist
total_tracks_added = 0
# Listen Later
if len(adder.listen_later) > 0 and len(conf.listen_later) > 0:
    listen_tracks_added = add_to_listen_to_later(spotify, adder.listen_later, conf.listen_later, conf.PLAYLIST_LIMIT)
    total_tracks_added += listen_tracks_added
    print('  *Added', listen_tracks_added, 'to Listen Later playlist.')

# Sets
if len(adder.sets) > 0 and len(conf.sets) > 0:
    sets_tracks_added = add_to_listen_to_later(spotify, adder.sets, conf.sets, conf.PLAYLIST_LIMIT)
    total_tracks_added += sets_tracks_added
    print('  *Added', sets_tracks_added, 'to Sets playlist.')
    
# compilations
if len(adder.compilations) > 0 and len(conf.compilations) > 0:
    comp_tracks_added = add_to_listen_to_later(spotify, adder.compilations, conf.compilations, conf.PLAYLIST_LIMIT)
    total_tracks_added += comp_tracks_added
    print('  *Added', comp_tracks_added, 'to Compilations playlist.')

# Logs
if len(logs_artist_tracks) > 0 or len(logs_playlist_tracks) > 0:
    write_logs(logs_artist_tracks, logs_playlist_tracks, conf)

# We're done here, now store when we last ran
set_last_run(conf)

print('Spot-Queuer Finished. Added', total_tracks_added, 'new songs.')