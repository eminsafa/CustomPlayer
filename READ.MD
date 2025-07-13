## Custom Player

```

pip install python-vlc pysrt pyinstaller

pyinstaller --onefile --windowed --icon=icon.ico --name MyPlayer --hidden-import=tkinter --hidden-import=vlc player.py




```


In Case
```
pyinstaller --onefile --windowed --icon=icon.ico --name MyPlayerApp ^
  --add-data "C:/Program Files/VideoLAN/VLC/plugins;vlc/plugins" ^
  --add-data "C:/Program Files/VideoLAN/VLC/libvlc.dll;." ^
  player.py

```