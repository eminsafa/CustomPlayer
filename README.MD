## Custom Player

```
# VLC
pip install python-vlc pysrt pyinstaller

# MPV 
pip install python-mpv pysrt pyinstaller
```

This is how to create a standalone executable

```
pyinstaller --onefile --windowed --icon=icon.ico --name CustomPlayer --add-data "C:/Program Files/VideoLAN/VLC/libvlc.dll;." --add-data "C:/Program Files/VideoLAN/VLC/libvlccore.dll;." --add-data "C:/Program Files/VideoLAN/VLC/plugins;plugins" player.py
```


```
pyinstaller --onefile --windowed --icon=icon.ico --name CustomPlayer --add-data "C:/Program Files/mpv/libmpv-2.dll;." via_mpv.py
```
