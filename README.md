# Artist Dodge

A browser game: load a Spotify playlist, pick one of its artists, choose how many songs you want to survive, then hit **Play**. Every **Next song** draws a random song from the playlist (no repeats). If a song by your artist comes up, you lose; if you get through your target number of songs without one, you win.

Everything is in `index.html`; no build step and no server.

## Spotify setup (one time)

1. Host the page over `https://` (for example with GitHub Pages) or open it at `http://127.0.0.1:<port>/`.
2. Create an app at https://developer.spotify.com/dashboard and add the page's URL as a Redirect URI. The page shows the exact URI to use under "Spotify setup".
3. Paste the app's Client ID into the page, paste a playlist link, and press **Scan playlist**.

Spotify-made playlists (Today's Top Hits, Daily Mixes and similar) can't be read by third-party apps. If you don't want to set up Spotify, use the **Paste songs** tab and enter `Artist - Title` lines instead.
