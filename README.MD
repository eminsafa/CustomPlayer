## Custom Player

```
pip install python-vlc pysrt pyinstaller
```

This is how to create a standalone executable

```
pyinstaller --onefile --windowed --icon=icon.ico --name CustomPlayer --add-data "C:/Program Files/VideoLAN/VLC/libvlc.dll;." --add-data "C:/Program Files/VideoLAN/VLC/libvlccore.dll;." --add-data "C:/Program Files/VideoLAN/VLC/plugins;plugins" player.py
```
