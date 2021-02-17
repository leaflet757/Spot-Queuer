import datetime
import sys
import tekore as tk


# Example usage:
# python src\spot-queuer.py C:\dev\projects\spot-queuer\user.data C:\dev\projects\spot-queuer\lastrun


def get_last_run(filename):
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

# Uncomment me to find playlist IDs, will not work if more that 20 playlists
#current_user = spotify.current_user()
#playlist_chunk = spotify.playlists(current_user.id, 20)
#for playlist in playlist_chunk.items:
#    print(playlist.name, playlist.id)
#exit()
# TODO:
# add a rollback time option
# get playlist count
# add new playlist songs

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
            #print('tts')
            for album in artist_albums.items:
                # increment the index regardless if we can add the album
                #print('why')
                album_date_split = album.release_date.split('-')
                if len(album_date_split) != 3:
                    if len(album_date_split) == 1:
                        print('  -%s date set to %s-1-1' % (album.name, album.release_date))
                        album_date = datetime.date(int(album_date_split[0]), 1, 1)
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
                    album_date = datetime.date(int(album_date_split[0]), int(album_date_split[1]), int(album_date_split[2]))
                #print('Album:', album_date, '-- run:', last_run)
                if album_date > last_run:
                    print('  *%s queueing' % (album.name))
                    to_add_albums.append((album.id, album.total_tracks, len(all_artists) - 1))
                #print('hmm')
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

num_added = 0
if to_add_length > 0:
    print('Finding album tracks...')
    
    for album_info in to_add_albums:
        album_id = album_info[0]
        album_track_num = album_info[1]
        target_artist = album_info[2]
        last_chunk_track_index = 0
        
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
                    if track_artist.id == target_artist:
                        shouldAdd = True
                if shouldAdd:
                    print('*%s by %s' % (track.name, track_artist.name))
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