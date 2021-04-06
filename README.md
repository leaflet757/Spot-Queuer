# Spot Queuer
I don't like seeing notifications on my phone unless they're important which was the main motivation behind this script. Instead of applications sending notifications for recently released tracks whenever the application determines is appropriate, this script allows the user to scan for new tracks whenever the user chooses to actually look for new tracks.

Example usage:
python src\spot-queuer.py \<user.data\> \<lastrun\> \<logs_path\> \[options\]

## Options
- -a : scan artists
- -p : scan playlists
- -d \<date\> : overwrite last artist and/or playlist run date, \<year-month-day,year-month-day\>
- -fp : print followed playlists

Running this will open up a webbrowser window asking to allow the script access of your Spotify
account. Scroll all the way to the bottom without reading any of the TOS and click the accept
button. This will open a new page to example.com. Copy the entire URL of this page and paste
it into the terminal window.

## User Data File
The \<user.data\> file must be in JSON format and be of the form:
```
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
```
## Last Run File
The \<lastrun\> file must only contain numbers separated by dashes for each last run category (artists,playlists):
```
year-month-day,year-month-day
```


## TODO
- display stale playlists
- Server Error 500
- check for track dups, uri check done - wat else?
- Playlists should check against timestamp
- Double adding song bug
- clean up this shitty code
- Add a queuer for followed podcasts
