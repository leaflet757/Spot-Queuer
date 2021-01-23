import datetime
import sys
import tekore as tk

def get_last_run(filename):
    print("Checking last run...")
    # If the date format is changed the my_date variable might need updating
    date_format = "%Y-%m-%d"
    
    f = open(filename,"r")
    date_split = f.read().split('-')
    f.close()

    my_date = datetime.date(int(date_split[0]), int(date_split[1]), int(date_split[2]))
    today = datetime.date.today()
    #today = datetime.date(2011, 1, 1)
    
    if today <= my_date:
        print('Already ran Spot-Queuer today. Smallest API precision is Day, exiting early.')
        exit()
    
    date_str = today.strftime(date_format)
    print('Writing new date', date_str)
    f = open(filename,"w")
    f.write(date_str)
    f.close()
    return today

def init_config(user_data_path):
    print('Loading User Config', user_data_path)
    client_id = ''
    client_secret = ''
    redirect_uri = ''
    
    f = open(user_data_path, 'r')
    for line in f:
        line = line.strip()
        tokens = line.split('=')
        if "client_id" == tokens[0]:
            client_id = tokens[1]
        if "client_secret" == tokens[0]:
            client_secret = tokens[1]
        if "redirect_uri" == tokens[0]:
            redirect_uri = tokens[1]
        if "listen_later" == tokens[0]:
            listen_later = tokens[1]
    f.close()
    
    assert len(client_id) > 0 and len(client_secret) > 0 and len(redirect_uri) > 0 and len(listen_later) > 0
    return (client_id, client_secret, redirect_uri, listen_later)


####################################################
#........................MAIN......................#
####################################################

print('Running Spot-Queuer...')

last_run = get_last_run(sys.argv[2])
conf = init_config(sys.argv[1])
token = tk.prompt_for_user_token(conf[0], conf[1], conf[2], scope=tk.scope.every)
spotify = tk.Spotify(token)

print('Authentication complete.')

# set up containers to cache the tracks/artists we will want to scan
to_add_albums = list()
to_add_tracks = list()
TRACK_LIMIT = 20
ARTIST_LIMIT = 50
ALBUM_LIMIT = 50
PLAYLIST_LIMIT = 100
MARKET = "US"
listen_later_playlist = ''
last_chunk_artist_id = ''
last_chunk_album_index = 0
last_chunk_track_index = 0

# Uncomment me to find playlist IDs, will not work if more that 20 playlists
#current_user = spotify.current_user()
#playlist_chunk = spotify.playlists(current_user.id, 20)
#for playlist in playlist_chunk.items:
    #print(playlist.name, playlist.id)
#exit()

followed_artists = spotify.followed_artists(limit=ARTIST_LIMIT)

while len(followed_artists.items) > 0:
    for artist in followed_artists.items:
        print('>>>Finding albums by', artist.name)
        artist_albums = spotify.artist_albums(artist_id=artist.id, market=MARKET, limit=ALBUM_LIMIT)
        last_chunk_album_index = 0
        while len(artist_albums.items) > 0:
            for album in artist_albums.items:
                album_date_split = album.release_date.split('-')
                assert(len(album_date_split) == 3)
                album_date = datetime.date(int(album_date_split[0]), int(album_date_split[1]), int(album_date_split[2]))
                if album_date > last_run:
                    print('Queuing', album.name, album.release_date)
                    to_add_albums.append((album.id, album.total_tracks))
                last_chunk_album_index += 1
            artist_albums = spotify.artist_albums(artist_id=artist.id, market=MARKET, limit=ALBUM_LIMIT, offset=last_chunk_album_index)
    last_chunk_artist_id = followed_artists.items[-1].id
    followed_artists = spotify.followed_artists(limit=ARTIST_LIMIT, after=last_chunk_artist_id)

to_add_length = len(to_add_albums)
print('Artist scan complete. Found', to_add_length, 'new albums.')

if to_add_length > 0:
    print('Finding album tracks...')
    
    for album_info in to_add_albums:
        album_id = album_info[0]
        album_track_num = album_info[1]
        last_chunk_track_index = 0
        
        while last_chunk_track_index < album_track_num:
            tracks = spotify.album_tracks(album_id, market=MARKET, limit=TRACK_LIMIT, offset=last_chunk_track_index)
            for track in tracks.items:
                to_add_tracks.append(track.uri)
            last_chunk_track_index += len(tracks.items)
    
    
    last_chunk_track_index = 0
    to_add_track_length = len(to_add_tracks)
    print('Found', to_add_track_length, 'tracks. Adding tracks to playlist...')
    # we know there is at least 1 item to add
    last_item = min(to_add_track_length, PLAYLIST_LIMIT)
    
    while last_chunk_track_index < last_item:
        #print('index:', last_chunk_track_index, 'last:', last_item)
        track_chunk = to_add_tracks[last_chunk_track_index:last_item]
        #print(len(track_chunk), track_chunk)
        spotify.playlist_add(conf[3], track_chunk)

        last_chunk_track_index = last_item
        last_item += min(to_add_track_length - last_item, PLAYLIST_LIMIT)


print('Spot-Queuer Finished.')