#import datetime as dt
from datetime import date
from datetime import datetime
import sys
import tekore as tk


# Example usage:
# python src\spot-queuer.py C:\dev\projects\spot-queuer\user.data C:\dev\projects\spot-queuer\lastrun

# TODO:
# Monstercat label exception
# display stale playlists
# check for track dups


def get_last_run(filename):
    # If the date format is changed the my_date variable might need updating
    date_format = "%Y-%m-%d"
    
    f = open(filename,"r")
    date_split = f.read().split('-')
    f.close()

    my_date = date(int(date_split[0]), int(date_split[1]), int(date_split[2]))
    today = date.today()
    #today = date(2011, 1, 1)
    
    if today <= my_date:
        print('Already ran Spot-Queuer today. Smallest API precision is Day, exiting early.')
        exit()
    
    date_str = today.strftime(date_format)
    print('Last run was on %s. Writing new date %s' % (my_date, today))
    f = open(filename,"w")
    f.write(date_str)
    f.close()
    return my_date

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

def get_user_playlists(user_data_path):
    print('Loading User Playlists', user_data_path)  
    f = open(user_data_path, 'r')
    for line in f:
        line = line.strip()
        tokens = line.split('=')
        if "playlists" == tokens[0]:
            listen_later = tokens[1]
            playlist_ids = listen_later.split(',')
    f.close()
    return playlist_ids

def write_logs(artist_tracks, playlist_tracks):
    f = open("info.log","w")
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
    # Close the file
    f.close()

####################################################
#........................MAIN......................#
####################################################

last_run = get_last_run(sys.argv[2])
conf = init_config(sys.argv[1])
token = tk.prompt_for_user_token(conf[0], conf[1], conf[2], scope=tk.scope.every)
spotify = tk.Spotify(token)

print('Authentication complete.')

# set up containers to cache the tracks/artists we will want to scan
to_add_albums = list()
to_add_tracks = list()
error_artists = list() #index0: artistname, index1: album index list
error_albums = list()
temp_list = list()
all_artists = list()
TRACK_LIMIT = 20
ARTIST_LIMIT = 50
ALBUM_LIMIT = 50
PLAYLIST_LIMIT = 100
MARKET = "US"
listen_later_playlist = ''
last_chunk_artist_id = ''
last_chunk_album_index = 0
last_chunk_track_index = 0
logs_artist_tracks = list()
logs_playlist_tracks = list()

# Uncomment me to find playlist IDs
#current_user = spotify.current_user()
#playlist_chunk = spotify.playlists(current_user.id, 20)
#last_playlist = 0
#while len(playlist_chunk.items) > 0:
#    for playlist in playlist_chunk.items:
#        print(playlist.name, playlist.id)
#    last_playlist += len(playlist_chunk.items)
#    playlist_chunk = spotify.playlists(current_user.id, 20, offset=last_playlist)
#exit()

followed_artists = spotify.followed_artists(limit=ARTIST_LIMIT)

while len(followed_artists.items) > 0:
    for artist in followed_artists.items:
        print('>>>%s' % artist.name)
        all_artists.append(artist.id)
        try:
            artist_albums = spotify.artist_albums(artist_id=artist.id, market=MARKET, limit=ALBUM_LIMIT)
        except tk.TooManyRequests as err:
            print(err.response)
            print('aborting.')
            exit()
        last_chunk_album_index = 0
        while len(artist_albums.items) > 0:
            for album in artist_albums.items:
                # increment the index regardless if we can add the album
                album_date_split = album.release_date.split('-')
                if len(album_date_split) != 3:
                    if len(album_date_split) == 1:
                        print('  -%s date set to %s-1-1' % (album.name, album.release_date))
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
                #print('Album:', album_date, '-- run:', last_run)
                if album_date >= last_run:
                    print('  *%s queueing' % (album.name))
                    to_add_albums.append((album.id, album.total_tracks, len(all_artists) - 1))
            last_chunk_album_index += len(artist_albums.items)
            #print('last chunk', last_chunk_album_index, 'num itesm', len(artist_albums.items))
            try:
                artist_albums = spotify.artist_albums(artist_id=artist.id, market=MARKET, limit=ALBUM_LIMIT, offset=last_chunk_album_index)
            except tk.TooManyRequests as err:
                print(err.response)
                print('aborting.')
                exit()
    last_chunk_artist_id = followed_artists.items[-1].id
    try:
        followed_artists = spotify.followed_artists(limit=ARTIST_LIMIT, after=last_chunk_artist_id)
    except tk.TooManyRequests as err:
        print(err.response)
        print('aborting.')
        exit()

to_add_length = len(to_add_albums)
print('Artist scan complete. Found', to_add_length, 'new albums.')

# Followed Artists
num_added = 0
if to_add_length > 0:
    print('Finding album tracks...')
    
    album_count = 0
    for album_info in to_add_albums:
        album_id = album_info[0]
        album_track_num = album_info[1]
        target_artist_id = album_info[2]
        last_chunk_track_index = 0

        album_count += 1
        if album_count % 50 == 1:
            print('Processing album chunk', album_count, 'of', to_add_length)
        
        while last_chunk_track_index < album_track_num:
            try:
                tracks = spotify.album_tracks(album_id, market=MARKET, limit=TRACK_LIMIT, offset=last_chunk_track_index)
            except tk.TooManyRequests as err:
                print(err.response)
                print('aborting.')
                exit()
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
    
# Specified Playlists
followed_playlists = get_user_playlists(sys.argv[1])
if len(followed_playlists) > 0:
    last_run_dt = datetime.combine(last_run, datetime.min.time())
    for playlist_id in followed_playlists:
        last_chunk_track_index = 0
        try:
            playlist_full = spotify.playlist(playlist_id, market=MARKET)
            playlist_tracks = spotify.playlist_items(playlist_id, market=MARKET, limit=PLAYLIST_LIMIT)
        except tk.TooManyRequests as err:
            print(err.response)
            print('aborting.')
            exit()
        print('>>>%s' % playlist_full.name)
        while len(playlist_tracks.items) > 0:
            for playlist_track in playlist_tracks.items:
                if playlist_track.added_at >= last_run_dt:
                    print('  *%s queueing' % playlist_track.track.name)
                    #TODO: enable me when the world is ready
                    #to_add_tracks.append(playlist_track.track.uri)
                    logs_playlist_tracks.append(('%s - %s' % (playlist_full.name, playlist_track.track.name)).encode('utf8'))
            last_chunk_track_index += len(playlist_tracks.items)
            try:
                playlist_tracks = spotify.playlist_items(playlist_id, market=MARKET, limit=PLAYLIST_LIMIT, offset=last_chunk_track_index)
            except tk.TooManyRequests as err:
                print(err.response)
                print('aborting.')
                exit()

if len(to_add_tracks) > 0:
    last_chunk_track_index = 0
    to_add_track_length = len(to_add_tracks)
    print('Found', to_add_track_length, 'new tracks. Adding tracks to playlist...')
    # we know there is at least 1 item to add
    last_item = min(to_add_track_length, PLAYLIST_LIMIT)
    
    while last_chunk_track_index < last_item:
        #print('index:', last_chunk_track_index, 'last:', last_item)
        track_chunk = to_add_tracks[last_chunk_track_index:last_item]
        print('Adding tracks', last_chunk_track_index, 'through', last_item)
        try:
            spotify.playlist_add(conf[3], track_chunk)
            num_added += len(track_chunk)
        except tk.TooManyRequests as err:
            print(err.response)
            print('aborting.')
            exit()
        last_chunk_track_index = last_item
        last_item += min(to_add_track_length - last_item, PLAYLIST_LIMIT)


print('Spot-Queuer Finished. Added', num_added, 'new songs.')

if len(error_albums) > 0:
    print('Spot-Queuer ran with errors :(\nCould not find release information for:')
    assert(len(error_albums) > 0 and len(error_artists) > 0)
    for artistPair in error_artists:
        print(artistPair[0])
        for index in artistPair[1]:
            print('  -%s' % error_albums[index])

if len(logs_artist_tracks) > 0 or len(logs_playlist_tracks) > 0:
    write_logs(logs_artist_tracks, logs_playlist_tracks)