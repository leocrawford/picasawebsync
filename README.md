# picasawebsync

This python utility will allow you to sync local directories with picasaweb. It is very much in beta state so please provide feedback

## Features

Currently it supports:

* Upload only (from local filesystem to picasaweb)
* Flattening (so that deep directroy hierarachies on the local filesystem are collapsed into a single web album)
* Smart web album naming (so that you can choose which elements of the directory path you'd like to retain)
* Large album support (so that directories with more than 1000 items are mapped to multiple sequenced web albums)
* Multi-layered approach to detecting file change, including timestamp, filesize and hash of file
* User-id and password log-on
* Install scripts

Soon to be supported:

* Two way sync (partially supported)
* Optional deletion (local and web)
* Support for browser based log-on so you don't need to tell the app your details

## Installation

1. Install you have python >=2.7 <3 installed (these version numbers are based on some assumptions, so I could be wrong), make sure it has SSL support enabled
2. Add the gdata packages 
    cd /tmp
    wget https://gdata-python-client.googlecode.com/files/gdata-2.0.17.zip
    unzip gdata*
    python setup.py install
3. download the latest version from the releases directory
4. untar it to a temporary directory (tar zxvf <filename> should work for most Linux distros)
5. (optionally) install it using 
    python setup.py install 
(you may need sudo for linux platforms)

## Executing it



    



Notes
--------

An upload can be one of:

upload: "none", "upload", "replace", "delete", "overwrite"
metadata: "none", "upload", "replace", "delete", "overwrite"


LOCAL_ONLY->Upload_local, Delete_local, Skip, Skip_report
REMOTE_ONLY->Download_remote, Delete_remote, Tag_remote, Skip, Skip_report
REMOTE_OLDER->Upload_local, Skip, Skip_report
DIFFERENT->Upload_local,Download_remote,Upload_local_metadata, Skip, Skip_report
SAME->Upload_local,Download_remote,Upload_local_metadata, Skip, Skip_report
UNKNOWN (No hash)->Upload_local,Download_remote,Upload_local_metadata, Skip, Skip_report

python setup.py sdist
