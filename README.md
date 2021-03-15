Example usage:
python src\spot-queuer.py <user.data> <lastrun> [options]

[options]
-a : scan artists
-p : scan playlists
-d <date> : overwrite last artist and playlist run date, <year-month-day,year-month-day>
-fp : print followed playlists

Running this will open up a webbrowser window asking to allow the script access of your Spotify
account. Scroll all the way to the bottom without reading any of the TOS and click the accept
button. This will open a new page to example.com. Copy the entire URL of this page and paste
it into the terminal window.

The <user.data> file must be in JSON format and be of the form:
{
    "user":
    {
        "client_id":"xxxxxxxxxx",
        "client_secret":"xxxxxxxxxxx",
        "redirect_uri":"https://example.com/callback",
        "listen_later":"xxxxxxxxxx"
    },
    "playlists":
    [  
        {
            "name":"Human Music Playlist",
            "id":"xxxxxxxxxx",
            "limit":"-1"
        },
    ]
}

TODO:
display stale playlists
Server Error 500
check for track dups, uri check done - wat else?
pick top rated songs from playlists
sort sets into separate playlist
clean up this shitty code