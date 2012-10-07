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
* Two way sync (partially supported)
* Optional deletion (remote side only)

Soon to be supported:

* Optional deletion (local side)
* Support for browser based log-on so you don't need to tell the app your details
* A better installation process. 

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

If you're able to help with a better installation process please shout

## Running it

### The basics 

The minimum command is 

    ./picasawebsync -u <username> -p <password> -d <one or more local directories>
    
Note: If python is installed in an usual place you might need to use:

    python picasawebsync -u <username> -p <password> -d <one or more local directories>

### The settings

#### Directory

The directory setting is a list of path names. They must all be directories. If any files are downloaded from a web album without a corresponding local album - it will be the first of these that is chosen.

#### Naming

Somehow we have to convert directory names into web album names. We could just have long strings with "/" seperators, but that isn't nice.

Instead we provide a rule to convert from a path name to a web album name. These are formed by a ~ seperated list of substitution paths (using python syntax for each)

For example

a/b/c/d formatted using {0} is a
a/b/c/d formatted using {0}~{1}-kkk-{0} is b-kkk-a
a/b/c/d formatted using {0}~{0}~{1}-kkk-{0} is b-kkk-a
a/b/c/d formatted using {0}~{0}~{0}~{0}~{1}-kkk-{0} is a
a/b/c/d formatted using {0}~{0}~{0}~{0}@{1}~{1}-kkk-{0} is a@b





    



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
