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
    f.close()
    
    assert len(client_id) > 0 and len(client_secret) > 0 and len(redirect_uri) > 0
    return (client_id, client_secret, redirect_uri)

####################################################
#........................MAIN......................#
####################################################
print('Running Spot-Queuer...')
last_run = get_last_run(sys.argv[2])
#conf = init_config(sys.argv[1])
token = tk.prompt_for_user_token(*conf, scope=tk.scope.every)
spotify = tk.Spotify(token)

print('Authentication complete.')

# set up containers to cache the tracks/artists we will want to scan
to_add_albums = list()
ARTIST_LIMIT = 50
ALBUM_LIMIT = 50
last_chunk_artist_id = ''
last_chunk_album_index = 0
last_chunk_track_index = 0

followed_artists = spotify.followed_artists(limit=ARTIST_LIMIT)
while len(followed_artists.items) > 0:
    for artist in followed_artists.items:
        print('Finding albums for artist', artist.name)
        artist_albums = spotify.artist_albums(artist_id=artist.id, market="US", limit=ALBUM_LIMIT)
        last_chunk_album_index = 0
        while len(artist_albums.items) > 0:
            for album in artist_albums.items:
                #print('Album:', album.name, ' Release Date:', album.release_date)
                last_chunk_album_index += 1
            artist_albums = spotify.artist_albums(artist_id=artist.id, market="US", limit=ALBUM_LIMIT, offset=last_chunk_album_index)
    last_chunk_artist_id = followed_artists.items[-1].id
    followed_artists = spotify.followed_artists(limit=ARTIST_LIMIT, after=last_chunk_artist_id)

if len(to_add_albums) > 0:
    print('TODO: Add tracks to playlist')
    for a in to_add_albums:
        print(a)

print('Spot-Queuer Finished.')